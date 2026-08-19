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

        /// <summary>POST 结算 PVE。checksum 可选，用于基础防篡改（seed+stage+结果）。</summary>
        public IEnumerator SettleBattleAsync(string battleId, bool win, int stars, int durationMs, string checksum, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"battle_id\":\"" + BaasJsonBody.Escape(battleId) + "\",\"win\":" + (win ? "true" : "false")
                + ",\"stars\":" + stars + ",\"duration_ms\":" + durationMs
                + ",\"checksum\":\"" + BaasJsonBody.Escape(checksum ?? string.Empty) + "\"}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/pve/battle/settle", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>生成与服务端一致的结算 checksum（可选）。</summary>
        public static string BuildChecksum(int seed, string stageId, bool win, int stars)
        {
            var raw = seed + ":" + (stageId ?? string.Empty) + ":" + (win ? 1 : 0) + ":" + stars;
            using (var sha = SHA256.Create())
            {
                var hash = sha.ComputeHash(Encoding.UTF8.GetBytes(raw));
                var sb = new StringBuilder();
                for (int i = 0; i < 8; i++) sb.Append(hash[i].ToString("x2"));
                return sb.ToString();
            }
        }
    }
}
