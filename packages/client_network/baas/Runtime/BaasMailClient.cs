using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    public sealed class BaasMailClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasMailClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        public IEnumerator GetInboxAsync(Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ResolveEndpoint("mail_inbox", "/mail/inbox");
            yield return BaasHttp.Get(url, _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator ClaimMailAsync(string mailId, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ResolveEndpoint("mail_claim", "/mail/" + Uri.EscapeDataString(mailId) + "/claim");
            yield return BaasHttp.PostJson(url, "{}", _ctx.PlayerHeaders(), onComplete);
        }
    }
}
