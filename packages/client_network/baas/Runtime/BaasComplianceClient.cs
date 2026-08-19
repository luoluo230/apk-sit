using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>防沉迷客户端。</summary>
    public sealed class BaasComplianceClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasComplianceClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>POST 开始游戏会话。</summary>
        public IEnumerator SessionStartAsync(bool realNameVerified, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"real_name_verified\":" + (realNameVerified ? "true" : "false") + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/compliance/session-start", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 心跳上报游玩时长。</summary>
        public IEnumerator HeartbeatAsync(int minutes, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"minutes\":" + minutes + "}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/compliance/heartbeat", body, _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 实名认证。</summary>
        public IEnumerator VerifyRealNameAsync(string name, string idNumber, Action<BaasApiResponse<string>> onComplete)
        {
            var body = BaasJsonBody.Object(("name", name ?? string.Empty), ("id_number", idNumber ?? string.Empty));
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/compliance/verify-real-name", body, _ctx.PlayerHeaders(), onComplete);
        }
    }
}
