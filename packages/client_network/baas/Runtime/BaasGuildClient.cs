using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>公会客户端。</summary>
    public sealed class BaasGuildClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasGuildClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>POST 创建公会。</summary>
        public IEnumerator CreateAsync(string name, Action<BaasApiResponse<string>> onComplete)
        {
            var body = BaasJsonBody.Object(("name", name ?? string.Empty));
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/guilds", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>GET 公会详情。</summary>
        public IEnumerator GetAsync(string guildId, Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/guilds/" + Uri.EscapeDataString(guildId), _ctx.ServiceHeaders(), onComplete);
        }

        /// <summary>POST 加入公会。</summary>
        public IEnumerator JoinAsync(string guildId, Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/guilds/" + Uri.EscapeDataString(guildId) + "/join", "{}", _ctx.PlayerHeaders(), onComplete);
        }
    }
}
