"""AFK home service tests: disposable SQL transactions; no production DB or project writes."""
import json
import os
import tempfile
os.environ["DATABASE_URL"] = ""
import config
config.DATA_DIR = tempfile.mkdtemp(prefix="afk-home-isolated-")
import sqlite3
import unittest
from contextlib import contextmanager, ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from flask import Flask
from services.baas import cloudsave_service as cloud, idle_service as idle, pve_service as pve
from services.baas.afk import afk_home_service as home


class AfkHomeContractTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
        CREATE TABLE baas_player_data(service_id TEXT,player_id TEXT,data_key TEXT,value_json TEXT,version INT,updated_at TEXT,PRIMARY KEY(service_id,player_id,data_key));
        CREATE TABLE baas_idle_state(service_id TEXT,player_id TEXT,last_claim_at TEXT,updated_at TEXT,PRIMARY KEY(service_id,player_id));
        CREATE TABLE baas_wallets(service_id TEXT,player_id TEXT,currency_id TEXT,balance INT,updated_at TEXT,PRIMARY KEY(service_id,player_id,currency_id));
        CREATE TABLE baas_chapter_progress(service_id TEXT,player_id TEXT,stage_id TEXT,stars INT,best_time_ms INT,cleared INT,updated_at TEXT,PRIMARY KEY(service_id,player_id,stage_id));
        CREATE TABLE baas_battles(battle_id TEXT PRIMARY KEY,service_id TEXT,player_id TEXT,battle_type TEXT,stage_id TEXT,status TEXT,team_json TEXT,result_json TEXT,settled_at TEXT,replay_hash TEXT);
        """)
        self.stack = ExitStack()
        for module in (home, idle, pve):
            self.stack.enter_context(patch.object(module, "get_cursor", self.cursor))
            self.stack.enter_context(patch.object(module, "init_db", lambda: None))
        for module in (idle, pve, cloud):
            self.stack.enter_context(patch.object(module, "feature_enabled", lambda *_: True))
            self.stack.enter_context(patch.object(module, "get_feature_config", lambda *_: {"stamina_max":120,"stamina_recover_seconds":360}))
        self.stack.enter_context(patch.object(idle,"_estimate_team_power", lambda *_: 100))
        self.stack.enter_context(patch.object(pve,"_vip_stamina_bonus",lambda *_: 0))
        self.stack.enter_context(patch.object(pve,"_group_stamina_add",lambda *_: 0))
        self.stack.enter_context(patch("services.baas.afk.afk_config_group.group_factors",lambda *_: {}))
        self.stack.enter_context(patch("services.baas.afk.afk_config_group.scale_rewards",lambda s,p,k,rewards: rewards))
        self.stack.enter_context(patch("services.baas.afk.afk_vip_service.idle_bonus_mul",lambda *_: 1))
        self.stack.enter_context(patch("services.baas.afk.afk_formula_engine.idle_item_rewards",lambda *_: {}))
        self.stack.enter_context(patch("services.baas.afk.afk_retention_hooks.on_idle_claim",lambda *_: None))
        self.stack.enter_context(patch("services.baas.afk.afk_retention_hooks.on_pve_win",lambda *a,**kw: None))

    def tearDown(self):
        self.stack.close()
        self.conn.close()

    @contextmanager
    def cursor(self):
        try:
            yield self.conn.cursor()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def clear_stage(self):
        self.conn.execute("INSERT INTO baas_chapter_progress VALUES ('s','p','AFK_01_10',3,3000,1,'now')")
        self.conn.commit()

    def ready_preview(self):
        self.clear_stage()
        first = idle.get_status('s','p')
        self.assertEqual(0,first['accumulated_minutes'])
        self.assertTrue(first['last_claim_at'])
        anchor = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self.conn.execute("UPDATE baas_idle_state SET last_claim_at=?",(anchor,))
        self.conn.commit()
        return idle.get_status('s','p')

    def test_fresh_home_and_first_unlock_create_a_real_accumulation_anchor(self):
        fresh = home.get_home('s','p')
        self.assertFalse(fresh['idle_eligible'])
        self.assertEqual(120,fresh['stamina_current'])
        self.assertEqual(1,fresh['account_level'])
        self.assertEqual(0,self.conn.execute("SELECT COUNT(*) FROM baas_idle_state").fetchone()[0])
        self.ready_preview()

    def test_claim_credits_three_resources_once_and_rejects_the_same_preview(self):
        preview = self.ready_preview()
        with patch.object(idle,'get_status',return_value=preview):
            result = idle.claim('s','p')
            self.assertEqual(preview['estimated_gold'],result['claimed_gold'])
            self.assertEqual(2,result['claimed_diamond'])
            self.assertEqual(preview['estimated_account_exp'],result['claimed_account_exp'])
            with self.assertRaisesRegex(ValueError,'已领取'): idle.claim('s','p')
        state = home.get_home('s','p')
        self.assertEqual(result['claimed_gold'],state['gold'])
        self.assertEqual(2,state['diamond'])
        self.assertEqual(result['claimed_account_exp'],state['account_exp_total'])
        self.assertEqual(0,state['idle_minutes'])
        self.assertEqual(0,home.get_home('s','other')['account_exp_total'])

    def test_zero_stamina_and_recovery_remainder_survive_reads(self):
        now = datetime.now(timezone.utc)
        payload = {"current":0,"updated_at":(now-timedelta(seconds=361)).isoformat()}
        with self.cursor() as cur: pve._save_stamina(cur,'s','p',payload)
        first = pve.get_stamina('s','p')['stamina']
        self.assertEqual(1,first['current'])
        age = (now-datetime.fromisoformat(first['updated_at'])).total_seconds()
        self.assertAlmostEqual(1,age,delta=.2)
        self.assertEqual(1,pve.get_stamina('s','p')['stamina']['current'])

    def test_pve_replay_does_not_award_account_experience_twice(self):
        plan = {"authority":{"win":True,"stars":3,"duration_ms":3000}}
        self.conn.execute("INSERT INTO baas_battles VALUES (?,?,?,?,?,?,?,?,?,?)",('b','s','p','pve','AFK_01_01','pending','{}',json.dumps(plan),'',''))
        self.conn.commit()
        with patch.object(pve,'_stage_def',return_value={'rewards':{'gold':100,'exp':60}}), patch.object(pve,'_grant_team_exp',return_value=[]):
            first = pve.settle_battle('s','p','b',win=False)
            again = pve.settle_battle('s','p','b',win=True)
        self.assertEqual(60,first['account']['account_exp_total'])
        self.assertEqual(60,again['account']['account_exp_total'])
        self.assertEqual(60,home.get_home('s','p')['account_exp_total'])
        self.assertEqual(100,home.get_home('s','p')['gold'])

    def test_cloud_save_cannot_forge_authoritative_xp_or_stamina(self):
        for key in ('_afk_account_progress','_pve_stamina'):
            with self.assertRaisesRegex(ValueError,'服务器管理'): cloud.put_key('s','p',key,{'total_exp':999999})

    def test_authenticated_http_home_route_returns_the_client_contract(self):
        from routes.baas import public_api
        app = Flask('afk-home-isolated-test')
        bp = __import__('flask').Blueprint('afk_home_test',__name__)
        public_api.register_baas_public_routes(bp)
        app.register_blueprint(bp)
        with patch.object(public_api,'_service_auth',return_value=('s',None)), patch.object(public_api,'_player_auth',return_value=({'player_id':'p'},None)):
            response = app.test_client().get('/api/baas/v1/s/afk/home')
        self.assertEqual(200,response.status_code)
        packet = response.get_json()
        self.assertTrue(packet['ok'])
        self.assertEqual(120,packet['data']['stamina_current'])
        self.assertGreater(packet['data']['server_utc_ticks'],0)
