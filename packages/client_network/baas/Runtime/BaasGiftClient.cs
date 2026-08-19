using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>礼包码客户端。</summary>
    public sealed class BaasGiftClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasGiftClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>POST 兑换礼包码。</summary>
        public IEnumerator RedeemAsync(string code, Action<BaasApiResponse<string>> onComplete)
        {
            var body = BaasJsonBody.Object(("code", code ?? string.Empty));
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/gifts/redeem", body, _ctx.PlayerHeaders(), onComplete);
        }
    }
}
