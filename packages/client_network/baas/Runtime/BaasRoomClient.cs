using System;
using System.Collections;
using MAClient.Network.Baas;

namespace MAClient.Network.Baas
{
    /// <summary>REST client for casual BaaS room + battle APIs.</summary>
    public sealed class BaasRoomClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;

        public BaasRoomClient(BaasClientContext context)
        {
            _ctx = context ?? throw new ArgumentNullException(nameof(context));
        }

        public BaasRoomClient(string portalBaseUrl, string serviceId, string apiKey, string playerToken = "", string playerId = "")
            : this(new BaasClientContext
            {
                PortalBaseUrl = portalBaseUrl,
                ServiceId = serviceId,
                ApiKey = apiKey,
                PublicApiBase = "/api/baas/v1/" + serviceId,
                PlayerToken = playerToken,
                PlayerId = playerId,
            })
        {
        }

        public BaasClientContext Context => _ctx;
        public string PlayerId => _ctx.PlayerId;
        public string PlayerToken => _ctx.PlayerToken;

        public void SetSession(string playerToken, string playerId) => _ctx.SetSession(playerToken, playerId);

        public IEnumerator GuestLoginAsync(string displayName, Action<BaasApiResponse<string>> onComplete)
        {
            var auth = new BaasAuthClient(_ctx);
            yield return auth.GuestLoginAsync(displayName, onComplete);
        }

        public IEnumerator MatchmakeAsync(string battleMode, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/pvp/matchmake";
            var body = "{\"battle_mode\":\"" + EscapeJson(battleMode) + "\"}";
            yield return BaasHttp.PostJson(url, body, _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator StartBattleAsync(string roomId, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/rooms/" + Uri.EscapeDataString(roomId) + "/start-battle";
            yield return BaasHttp.PostJson(url, "{}", _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator SyncStateAsync(string roomId, string stateJson, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/pvp/rooms/" + Uri.EscapeDataString(roomId) + "/state";
            var body = "{\"state\":" + (string.IsNullOrWhiteSpace(stateJson) ? "{}" : stateJson) + "}";
            yield return BaasHttp.PostJson(url, body, _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator PushFrameAsync(string roomId, string frameJson, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/rooms/" + Uri.EscapeDataString(roomId) + "/frames";
            var body = "{\"frame\":" + (string.IsNullOrWhiteSpace(frameJson) ? "{}" : frameJson) + "}";
            yield return BaasHttp.PostJson(url, body, _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator PollFramesAsync(string roomId, int sinceSeq, int waitMs, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/rooms/" + Uri.EscapeDataString(roomId)
                + "/frames?since_seq=" + sinceSeq + "&wait_ms=" + Math.Max(0, waitMs);
            var headers = _ctx.ServiceHeaders();
            headers["X-Baas-Player-Id"] = _ctx.PlayerId;
            yield return BaasHttp.Get(url, headers, onComplete, Math.Max(10, waitMs / 1000 + 5));
        }

        public IEnumerator FinishBattleAsync(string roomId, string resultJson, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/rooms/" + Uri.EscapeDataString(roomId) + "/finish-battle";
            var body = "{\"result\":" + (string.IsNullOrWhiteSpace(resultJson) ? "{}" : resultJson) + "}";
            yield return BaasHttp.PostJson(url, body, _ctx.PlayerHeaders(), onComplete);
        }

        static string EscapeJson(string value) => (value ?? string.Empty).Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}
