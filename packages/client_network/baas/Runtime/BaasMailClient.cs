using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>邮件客户端：收件箱查询与领取附件/奖励。</summary>
    public sealed class BaasMailClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasMailClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>GET 收件箱列表。</summary>
        public IEnumerator GetInboxAsync(Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ResolveEndpoint("mail_inbox", "/mail/inbox");
            yield return BaasHttp.Get(url, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 领取指定邮件。</summary>
        public IEnumerator ClaimMailAsync(string mailId, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ResolveEndpoint("mail_claim", "/mail/" + Uri.EscapeDataString(mailId) + "/claim");
            yield return BaasHttp.PostJson(url, "{}", _ctx.PlayerHeaders(), onComplete);
        }
    }
}
