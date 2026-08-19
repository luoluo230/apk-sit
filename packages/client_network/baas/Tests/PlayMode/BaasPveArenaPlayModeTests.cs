using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace MAClient.Network.Baas.PlayModeTests
{
    public class BaasPveArenaPlayModeTests
    {
        static BaasNetworkSettings BuildSettings()
        {
            var portal = System.Environment.GetEnvironmentVariable("BAAS_E2E_PORTAL") ?? "http://127.0.0.1:5004";
            var gameId = System.Environment.GetEnvironmentVariable("BAAS_E2E_GAME_ID") ?? "baas-production-e2e";
            var gameKey = System.Environment.GetEnvironmentVariable("BAAS_E2E_GAME_KEY") ?? "baas-production-e2e-key";
            var apiKey = System.Environment.GetEnvironmentVariable("BAAS_E2E_API_KEY") ?? string.Empty;
            if (string.IsNullOrEmpty(apiKey))
                Assert.Ignore("BAAS_E2E_API_KEY not set");
            var settings = ScriptableObject.CreateInstance<BaasNetworkSettings>();
            settings.PortalBaseUrl = portal;
            settings.GameId = gameId;
            settings.GameKey = gameKey;
            settings.ApiKey = apiKey;
            settings.AutoGuestLoginAfterBootstrap = true;
            return settings;
        }

        static IEnumerator Bootstrap(BaasNetworkSettings settings, System.Action<BaasFeatureHub> onReady)
        {
            var svc = new BaasBootstrapService(settings);
            bool ok = false;
            string err = null;
            yield return svc.BootstrapCoroutine((success, error) => { ok = success; err = error; });
            Assert.IsTrue(ok, err ?? "bootstrap failed");
            onReady?.Invoke(new BaasFeatureHub(svc.Context));
        }

        [UnityTest]
        public IEnumerator Pve_start_simulate_settle_updates_progress()
        {
            var settings = BuildSettings();
            BaasFeatureHub hub = null;
            yield return Bootstrap(settings, h => hub = h);

            var team = BaasSeedBattleSimulator.HeroesTeamJson(new[] { 1, 2, 3 });
            BaasApiResponse<string> startResp = null;
            yield return hub.Pve.StartBattleAsync("1-1", team, r => startResp = r);
            Assert.IsTrue(startResp != null && startResp.ok, (startResp?.UserMessage ?? "pve start failed") + " body=" + (startResp?.raw_body ?? ""));
            var battleId = BaasApiResponse<string>.ExtractString(startResp.data, "battle_id");
            var seed = BaasApiResponse<string>.ExtractInt(startResp.data, "seed");
            Assert.Greater(seed, 0, "seed missing in start response: " + (startResp.data ?? ""));
            var sim = BaasSeedBattleSimulator.SimulatePve(seed, new[] { 1, 2, 3 });
            var checksum = BaasPveClient.BuildChecksum(seed, "1-1", sim.Win, sim.Stars);
            var replayHash = BaasPveClient.BuildReplayHash(seed, "pve", sim.TeamJson, sim.Win, sim.Ticks);
            BaasApiResponse<string> settleResp = null;
            yield return hub.Pve.SettleBattleAsync(
                battleId, sim.Win, sim.Stars, sim.DurationMs, checksum, replayHash, sim.Ticks,
                r => settleResp = r);
            Assert.IsTrue(settleResp != null && settleResp.ok, settleResp?.UserMessage ?? "pve settle failed");
        }

        [UnityTest]
        public IEnumerator Arena_two_players_defense_and_settle()
        {
            var settings = BuildSettings();
            settings.GuestDisplayName = "ArenaDefender";
            BaasFeatureHub defenderHub = null;
            yield return Bootstrap(settings, h => defenderHub = h);
            var defJson = BaasSeedBattleSimulator.HeroesTeamJson(new[] { 21, 22 });
            var defPower = BaasSeedBattleSimulator.SumHeroPower(new[] { 21, 22 });
            BaasApiResponse<string> defResp = null;
            yield return defenderHub.Arena.UpdateDefenseAsync(defJson, defPower, r => defResp = r);
            Assert.IsTrue(defResp != null && defResp.ok, defResp?.UserMessage ?? "defense failed");
            var defenderPlayerId = defenderHub.Context.PlayerId;

            settings.GuestDisplayName = "ArenaAttacker";
            BaasFeatureHub attackerHub = null;
            yield return Bootstrap(settings, h => attackerHub = h);

            var team = BaasSeedBattleSimulator.HeroesTeamJson(new[] { 1, 2 });
            BaasApiResponse<string> startResp = null;
            yield return attackerHub.Arena.StartBattleAsync(defenderPlayerId, team, r => startResp = r);
            Assert.IsTrue(startResp != null && startResp.ok, startResp?.UserMessage ?? "arena start failed");
            var battleId = BaasApiResponse<string>.ExtractString(startResp.data, "battle_id");
            var seed = BaasApiResponse<string>.ExtractInt(startResp.data, "seed");
            Assert.Greater(seed, 0);
            var sim = BaasSeedBattleSimulator.SimulateArena(seed, new[] { 1, 2 }, new[] { 21, 22 });
            var checksum = BaasArenaClient.BuildChecksum(seed, defenderPlayerId, sim.Win);
            var replayHash = BaasArenaClient.BuildReplayHash(seed, sim.TeamJson, defenderPlayerId, sim.Win, sim.Ticks);
            BaasApiResponse<string> settleResp = null;
            yield return attackerHub.Arena.SettleBattleAsync(
                battleId, sim.Win, sim.DurationMs, checksum, replayHash, sim.Ticks,
                r => settleResp = r);
            Assert.IsTrue(settleResp != null && settleResp.ok, (settleResp?.UserMessage ?? "arena settle failed") + " body=" + (settleResp?.raw_body ?? ""));
        }
    }
}
