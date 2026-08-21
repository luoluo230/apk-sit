using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>抽卡召唤：卡池列表、pity、单抽/十连。</summary>
    public sealed class BaasGachaClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;
        public BaasGachaClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        public IEnumerator ListPoolsAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/gacha/pools", _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator GetPityAsync(string poolId, Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/gacha/" + Uri.EscapeDataString(poolId) + "/pity", _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator PullAsync(string poolId, int count, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"count\":" + Math.Max(1, count) + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/gacha/" + Uri.EscapeDataString(poolId) + "/pull", body, _ctx.PlayerHeaders(), onComplete);
        }
    }
}
