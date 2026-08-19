using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

namespace MAClient.Network.Baas
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
    /// Bootstrap helper for casual BaaS REST client module.
    /// </summary>
    public sealed class BaasNetworkModule
    {
        public const string DefaultBootstrapPath = "/api/public/client-bootstrap";

        public string PortalBaseUrl { get; private set; }
        public string ServiceId { get; private set; }
        public string ApiKey { get; private set; }
        public string PublicApiBase { get; private set; }

        public IEnumerator BootstrapCoroutine(
            string portalBaseUrl,
            string gameId,
            string gameKey,
            string envKey,
            string apiKey,
            Action<BaasBootstrapResponse, string> onComplete)
        {
            PortalBaseUrl = portalBaseUrl.TrimEnd('/');
            ApiKey = apiKey;
            var qs = "game_id=" + Uri.EscapeDataString(gameId)
                + "&game_key=" + Uri.EscapeDataString(gameKey)
                + "&env_key=" + Uri.EscapeDataString(envKey ?? "development");
            var url = PortalBaseUrl + DefaultBootstrapPath + "?" + qs;
            yield return BaasHttp.Get(url, null, (json, err) =>
            {
                if (!string.IsNullOrEmpty(err)) { onComplete?.Invoke(null, err); return; }
                var resp = JsonUtility.FromJson<BaasBootstrapResponse>(json);
                if (resp == null || !resp.ok)
                {
                    onComplete?.Invoke(null, "baas bootstrap failed");
                    return;
                }
                ServiceId = resp.service_id;
                PublicApiBase = resp.public_api_base;
                Debug.Log("[BaasNetwork] base=" + PublicApiBase);
                onComplete?.Invoke(resp, null);
            });
        }

        public Dictionary<string, string> ServiceHeaders()
        {
            return new Dictionary<string, string>
            {
                ["X-Baas-Api-Key"] = ApiKey ?? string.Empty,
                ["X-Baas-Service-Id"] = ServiceId ?? string.Empty,
            };
        }

        public string Url(string relativePath)
        {
            var basePath = string.IsNullOrEmpty(PublicApiBase) ? string.Empty : PublicApiBase.TrimEnd('/');
            return PortalBaseUrl + basePath + relativePath;
        }
    }
}
