using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>周期任务客户端。</summary>
    public sealed class BaasTaskClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasTaskClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>GET 任务列表。</summary>
        public IEnumerator ListAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/tasks", _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 上报任务进度。</summary>
        public IEnumerator ReportProgressAsync(string taskId, int progress, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/tasks/" + Uri.EscapeDataString(taskId) + "/progress";
            var body = "{\"progress\":" + progress + "}";
            yield return BaasHttp.PostJson(url, body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 领取任务奖励。</summary>
        public IEnumerator ClaimAsync(string taskId, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/tasks/" + Uri.EscapeDataString(taskId) + "/claim";
            yield return BaasHttp.PostJson(url, "{}", _ctx.PlayerHeaders(), onComplete);
        }
    }
}
