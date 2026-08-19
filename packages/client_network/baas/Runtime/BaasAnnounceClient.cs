using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>公告客户端：拉取当前有效公告。</summary>
    public sealed class BaasAnnounceClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasAnnounceClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>GET 有效公告。displayType 例如 login / lobby。</summary>
        public IEnumerator GetActiveAsync(string displayType, Action<BaasApiResponse<string>> onComplete)
        {
            string qs = string.IsNullOrEmpty(displayType) ? "" : "?display_type=" + Uri.EscapeDataString(displayType);
            string url = _ctx.ResolveEndpoint("announce", "/announcements/active") + qs;
            yield return BaasHttp.Get(url, _ctx.ServiceHeaders(), onComplete);
        }
    }
}
