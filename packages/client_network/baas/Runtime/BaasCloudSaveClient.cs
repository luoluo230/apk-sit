using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    public sealed class BaasCloudSaveClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasCloudSaveClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        public IEnumerator GetAsync(string key, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ResolveEndpoint("cloudsave_get", "/cloudsave/" + Uri.EscapeDataString(key));
            yield return BaasHttp.Get(url, _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator PutAsync(string key, string valueJson, int expectedVersion, Action<BaasApiResponse<string>> onComplete)
        {
            string url = _ctx.ResolveEndpoint("cloudsave_put", "/cloudsave/" + Uri.EscapeDataString(key));
            var body = "{\"value\":" + (string.IsNullOrWhiteSpace(valueJson) ? "null" : valueJson) + ",\"expected_version\":" + expectedVersion + "}";
            yield return BaasHttp.PostJson(url, body, _ctx.PlayerHeaders(), onComplete);
        }
    }
}
