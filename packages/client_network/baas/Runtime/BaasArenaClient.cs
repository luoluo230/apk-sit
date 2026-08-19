using System;
using System.Collections;
using System.Security.Cryptography;
using System.Text;

namespace MAClient.Network.Baas
{
    /// <summary>
    /// 异步竞技场客户端（剑与远征式挑战玩家离线防守数据）。
    /// 流程：更新防守 → 拉对手 → 开战 → 客户端模拟 → 结算(积分+奖励)。
    /// </summary>
    public sealed class BaasArenaClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasArenaClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>GET 竞技场状态（积分、胜败、今日次数）。</summary>
        public IEnumerator GetStateAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/arena/state", _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 更新自己的防守阵容快照。defenseJson 例如 {"heroes":[11,12]}。</summary>
        public IEnumerator UpdateDefenseAsync(string defenseJson, int power, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"power\":" + power + ",\"defense\":" + (string.IsNullOrWhiteSpace(defenseJson) ? "{}" : defenseJson) + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/arena/defense", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>GET 可挑战对手列表。</summary>
        public IEnumerator ListOpponentsAsync(int count, Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/arena/opponents?count=" + Math.Max(1, count), _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>GET 指定玩家防守详情（开战前预览）。</summary>
        public IEnumerator GetDefenseAsync(string playerId, Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/arena/defense?player_id=" + Uri.EscapeDataString(playerId), _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 开始竞技场战斗。</summary>
        public IEnumerator StartBattleAsync(string defenderId, string teamJson, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"defender_id\":\"" + BaasJsonBody.Escape(defenderId) + "\",\"team\":" + (string.IsNullOrWhiteSpace(teamJson) ? "{}" : teamJson) + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/arena/battle/start", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 结算竞技场战斗。</summary>
        public IEnumerator SettleBattleAsync(
            string battleId,
            bool win,
            int durationMs,
            string checksum,
            string replayHash,
            int replayTicks,
            Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"battle_id\":\"" + BaasJsonBody.Escape(battleId) + "\",\"win\":" + (win ? "true" : "false")
                + ",\"duration_ms\":" + durationMs + ",\"checksum\":\"" + BaasJsonBody.Escape(checksum ?? string.Empty) + "\""
                + ",\"replay_hash\":\"" + BaasJsonBody.Escape(replayHash ?? string.Empty) + "\""
                + ",\"replay_ticks\":" + Math.Max(0, replayTicks) + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/arena/battle/settle", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>生成竞技场结算 checksum。</summary>
        public static string BuildChecksum(int seed, string defenderId, bool win)
        {
            var raw = seed + ":" + (defenderId ?? string.Empty) + ":" + (win ? 1 : 0);
            return Sha16(raw);
        }

        /// <summary>生成竞技场 replay hash。</summary>
        public static string BuildReplayHash(int seed, string teamJson, string defenderId, bool win, int ticks)
        {
            return BaasPveClient.BuildReplayHash(seed, "arena", teamJson, win, ticks, defenderId);
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
