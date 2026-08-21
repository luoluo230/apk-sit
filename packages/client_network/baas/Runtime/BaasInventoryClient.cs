using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>背包：道具列表、消耗。</summary>
    public sealed class BaasInventoryClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;
        public BaasInventoryClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        public IEnumerator ListAsync(string itemType, Action<BaasApiResponse<string>> onComplete)
        {
            var q = string.IsNullOrWhiteSpace(itemType) ? "" : "?type=" + Uri.EscapeDataString(itemType);
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/inventory" + q, _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator UseAsync(string itemUid, int quantity, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"quantity\":" + Math.Max(1, quantity) + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/inventory/" + Uri.EscapeDataString(itemUid) + "/use", body, _ctx.PlayerHeaders(), onComplete);
        }
    }
}
