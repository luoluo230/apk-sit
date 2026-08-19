using System;
using System.Collections;
using System.Security.Cryptography;
using System.Text;

namespace MAClient.Network.Baas
{
    /// <summary>
    /// PVE 推图客户端（剑与远征式主线）。
    /// 流程：查体力/进度 → 开战(扣体力+拿 seed) → 客户端模拟 → 结算(服务端写进度+发奖)。
    /// </summary>
    public sealed class BaasPveClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasPveClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>GET 当前体力。</summary>
        public IEnumerator GetStaminaAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/pve/stamina", _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>GET 章节关卡进度（星数、通关状态）。</summary>
        public IEnumerator GetProgressAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/pve/progress", _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 开始 PVE 战斗。teamJson 为阵容 JSON 字符串，例如 {"heroes":[1,2,3]}。</summary>
        public IEnumerator StartBattleAsync(string stageId, string teamJson, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"stage_id\":\"" + BaasJsonBody.Escape(stageId) + "\",\"team\":"
                + (string.IsNullOrWhiteSpace(teamJson) ? "{}" : teamJson) + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/pve/battle/start", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 结算 PVE。checksum / replay_hash 用于防篡改与回放摘要校验。</summary>
        public IEnumerator SettleBattleAsync(
            string battleId,
            bool win,
            int stars,
            int durationMs,
            string checksum,
            string replayHash,
            int replayTicks,
            Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"battle_id\":\"" + BaasJsonBody.Escape(battleId) + "\",\"win\":" + (win ? "true" : "false")
                + ",\"stars\":" + stars + ",\"duration_ms\":" + durationMs
                + ",\"checksum\":\"" + BaasJsonBody.Escape(checksum ?? string.Empty) + "\""
                + ",\"replay_hash\":\"" + BaasJsonBody.Escape(replayHash ?? string.Empty) + "\""
                + ",\"replay_ticks\":" + Math.Max(0, replayTicks) + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/pve/battle/settle", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>生成与服务端一致的结算 checksum。</summary>
        public static string BuildChecksum(int seed, string stageId, bool win, int stars)
        {
            var raw = seed + ":" + (stageId ?? string.Empty) + ":" + (win ? 1 : 0) + ":" + stars;
            return Sha16(raw);
        }

        /// <summary>生成与服务端一致的 replay hash（需与 BaasSeedBattleSimulator 输出一致）。</summary>
        public static string BuildReplayHash(int seed, string battleType, string teamJson, bool win, int ticks, string defenderId = "")
        {
            var normalizedTeam = string.IsNullOrWhiteSpace(teamJson) ? "{}" : teamJson.Trim();
            var raw = seed + ":" + (battleType ?? string.Empty) + ":" + normalizedTeam + ":"
                + (defenderId ?? string.Empty) + ":" + (win ? 1 : 0) + ":" + Math.Max(0, ticks);
            return Sha16(raw);
        }

        static string Sha16(string raw)
        {
            using (var sha = SHA256.Create())
            {
                var hash = sha.ComputeHash(Encoding.UTF8.GetBytes(raw ?? string.Empty));
                var sb = new StringBuilder();
                for (int i = 0; i < 8; i++) sb.Append(hash[i].ToString("x2"));
                return sb.ToString();
            }
        }
    }
}
