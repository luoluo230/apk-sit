using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>成就客户端。</summary>
    public sealed class BaasAchievementClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasAchievementClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>GET 成就列表与进度。</summary>
        public IEnumerator ListAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/achievements", _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 上报成就进度。</summary>
        public IEnumerator ReportProgressAsync(string achievementId, int progress, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/achievements/" + Uri.EscapeDataString(achievementId) + "/progress";
            var body = "{\"progress\":" + progress + "}";
            yield return BaasHttp.PostJson(url, body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 领取成就奖励。</summary>
        public IEnumerator ClaimAsync(string achievementId, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/achievements/" + Uri.EscapeDataString(achievementId) + "/claim";
            yield return BaasHttp.PostJson(url, "{}", _ctx.PlayerHeaders(), onComplete);
        }
    }
}
