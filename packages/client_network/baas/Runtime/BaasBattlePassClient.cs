using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>战令客户端。</summary>
    public sealed class BaasBattlePassClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasBattlePassClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>GET 战令状态。</summary>
        public IEnumerator GetStateAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/battlepass", _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 增加战令经验。</summary>
        public IEnumerator AddXpAsync(int xp, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"xp\":" + xp + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/battlepass/xp", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 领取战令等级奖励。</summary>
        public IEnumerator ClaimAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/battlepass/claim", "{}", _ctx.PlayerHeaders(), onComplete);
        }
    }
}
