using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>挂机离线收益：查询累计、一键领取。</summary>
    public sealed class BaasIdleClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;
        public BaasIdleClient(BaasClientContext ctx) { _ctx = ctx ?? throw new System.ArgumentNullException(nameof(ctx)); }

        public IEnumerator GetStatusAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/idle/status", _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator ClaimAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/idle/claim", "{}", _ctx.PlayerHeaders(), onComplete);
        }
    }
}
