using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>爬塔副本：进度、开战、结算（checksum 规则与 PVE 相同，stage_key 为 towerId:floor）。</summary>
    public sealed class BaasTowerClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;
        public BaasTowerClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        public IEnumerator GetProgressAsync(string towerId, Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/tower/" + Uri.EscapeDataString(towerId) + "/progress", _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator StartBattleAsync(string towerId, int floor, string teamJson, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"floor\":" + floor + ",\"team\":" + (string.IsNullOrWhiteSpace(teamJson) ? "{}" : teamJson) + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/tower/" + Uri.EscapeDataString(towerId) + "/battle/start", body, _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator SettleBattleAsync(
            string battleId, bool win, int stars, int durationMs, string checksum, string replayHash, int replayTicks,
            Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"battle_id\":\"" + BaasJsonBody.Escape(battleId) + "\",\"win\":" + (win ? "true" : "false")
                + ",\"stars\":" + stars + ",\"duration_ms\":" + durationMs
                + ",\"checksum\":\"" + BaasJsonBody.Escape(checksum ?? "") + "\""
                + ",\"replay_hash\":\"" + BaasJsonBody.Escape(replayHash ?? "") + "\""
                + ",\"replay_ticks\":" + Math.Max(0, replayTicks) + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/tower/battle/settle", body, _ctx.PlayerHeaders(), onComplete);
        }

        public static string BuildChecksum(int seed, string stageKey, bool win, int stars)
            => BaasPveClient.BuildChecksum(seed, stageKey, win, stars);

        public static string BuildReplayHash(int seed, string teamJson, bool win, int ticks)
            => BaasPveClient.BuildReplayHash(seed, "tower", teamJson, win, ticks);
    }
}
