using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    public sealed class BaasAuthClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasAuthClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        public IEnumerator GuestLoginAsync(string displayName, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/auth/guest";
            var body = "{\"display_name\":\"" + EscapeJson(displayName) + "\"}";
            yield return BaasHttp.PostJson(url, body, _ctx.ServiceHeaders(), resp =>
            {
                if (resp.ok)
                {
                    var token = BaasApiResponse<string>.ExtractString(resp.data ?? string.Empty, "token");
                    var pid = BaasApiResponse<string>.ExtractString(resp.data ?? string.Empty, "player_id");
                    if (!string.IsNullOrEmpty(token) && !string.IsNullOrEmpty(pid))
                        _ctx.SetSession(token, pid);
                }
                onComplete?.Invoke(resp);
            });
        }

        public IEnumerator RegisterAsync(string username, string password, string displayName, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/auth/register";
            var body = "{\"username\":\"" + EscapeJson(username) + "\",\"password\":\"" + EscapeJson(password) + "\",\"display_name\":\"" + EscapeJson(displayName) + "\"}";
            yield return BaasHttp.PostJson(url, body, _ctx.ServiceHeaders(), onComplete);
        }

        public IEnumerator LoginAsync(string username, string password, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ApiPrefix + "/auth/login";
            var body = "{\"username\":\"" + EscapeJson(username) + "\",\"password\":\"" + EscapeJson(password) + "\"}";
            yield return BaasHttp.PostJson(url, body, _ctx.ServiceHeaders(), resp =>
            {
                if (resp.ok)
                {
                    var token = BaasApiResponse<string>.ExtractString(resp.data ?? string.Empty, "token");
                    var pid = BaasApiResponse<string>.ExtractString(resp.data ?? string.Empty, "player_id");
                    if (!string.IsNullOrEmpty(token) && !string.IsNullOrEmpty(pid))
                        _ctx.SetSession(token, pid);
                }
                onComplete?.Invoke(resp);
            });
        }

        static string EscapeJson(string value) => (value ?? string.Empty).Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}
