using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>排行榜客户端：提交分数、查询榜单。</summary>
    public sealed class BaasLeaderboardClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasLeaderboardClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>POST 提交分数到指定榜单。</summary>
        public IEnumerator SubmitScoreAsync(string boardId, float score, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/leaderboards/" + Uri.EscapeDataString(boardId) + "/submit";
            var body = "{\"score\":" + score.ToString(System.Globalization.CultureInfo.InvariantCulture) + "}";
            yield return BaasHttp.PostJson(url, body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>GET 榜单 Top N。</summary>
        public IEnumerator GetTopAsync(string boardId, int limit, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/leaderboards/" + Uri.EscapeDataString(boardId)
                + "/top?limit=" + Math.Max(1, limit);
            yield return BaasHttp.Get(url, _ctx.ServiceHeaders(), onComplete);
        }
    }
}
