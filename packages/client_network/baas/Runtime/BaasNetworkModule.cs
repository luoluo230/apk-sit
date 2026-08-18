// BaaS client network module — pairs with casual_baas_server.
// Copy Runtime/ + ../common/Runtime/PortalHttp.cs to Unity project.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Game.Network.Common;
using UnityEngine;

namespace Game.Network.Baas
{
    [Serializable]
    public class BaasBootstrapResponse
    {
        public bool ok;
        public string framework;
        public string client_module;
        public string bootstrap_kind;
        public string service_id;
        public string public_api_base;
        public string auth_header_service;
        public string auth_header_key;
    }

    /// <summary>
    /// Fetches client-bootstrap and configures REST client base URL.
    /// </summary>
    public class BaasNetworkModule
    {
        public const string DefaultBootstrapPath = "/api/public/client-bootstrap";

        public string PortalBaseUrl { get; private set; }
        public string ServiceId { get; private set; }
        public string ApiKey { get; private set; }
        public string PublicApiBase { get; private set; }

        public async Task<BaasBootstrapResponse> BootstrapAsync(
            string portalBaseUrl,
            string gameId,
            string gameKey,
            string envKey,
            string apiKey)
        {
            PortalBaseUrl = portalBaseUrl.TrimEnd('/');
            ApiKey = apiKey;
            var qs = new Dictionary<string, string>
            {
                ["game_id"] = gameId,
                ["game_key"] = gameKey,
                ["env_key"] = envKey,
            };
            var url = PortalBaseUrl + DefaultBootstrapPath + "?" + BuildQuery(qs);
            var json = await PortalHttp.GetAsync(url);
            var resp = JsonUtility.FromJson<BaasBootstrapResponse>(json);
            if (resp == null || !resp.ok)
                throw new InvalidOperationException("baas bootstrap failed");
            ServiceId = resp.service_id;
            PublicApiBase = resp.public_api_base;
            Debug.Log("[BaasNetwork] base=" + PublicApiBase);
            return resp;
        }

        public Dictionary<string, string> ServiceHeaders()
        {
            return new Dictionary<string, string>
            {
                ["X-Baas-Api-Key"] = ApiKey ?? "",
                ["X-Baas-Service-Id"] = ServiceId ?? "",
            };
        }

        public string Url(string relativePath)
        {
            var basePath = string.IsNullOrEmpty(PublicApiBase) ? "" : PublicApiBase.TrimEnd('/');
            return PortalBaseUrl + basePath + relativePath;
        }

        static string BuildQuery(Dictionary<string, string> kv)
        {
            var parts = new List<string>();
            foreach (var p in kv)
                parts.Add(Uri.EscapeDataString(p.Key) + "=" + Uri.EscapeDataString(p.Value ?? ""));
            return string.Join("&", parts);
        }
    }
}
