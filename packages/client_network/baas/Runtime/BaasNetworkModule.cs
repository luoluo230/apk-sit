using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

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
        public string error_code;
        public string error;
    }

    /// <summary>Bootstrap helper for casual BaaS REST client module.</summary>
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
            Action<BaasBootstrapResponse, string> onComplete,
            Action<string> onRawJson = null)
        {
            PortalBaseUrl = portalBaseUrl.TrimEnd('/');
            ApiKey = apiKey;
            var qs = "game_id=" + Uri.EscapeDataString(gameId)
                + "&game_key=" + Uri.EscapeDataString(gameKey)
                + "&env_key=" + Uri.EscapeDataString(envKey ?? "development");
            var url = PortalBaseUrl + DefaultBootstrapPath + "?" + qs;
            yield return BaasHttp.Get(url, null, resp =>
            {
                var raw = string.IsNullOrEmpty(resp.raw_body) ? (resp.data ?? string.Empty) : resp.raw_body;
                onRawJson?.Invoke(raw);
                if (!resp.ok)
                {
                    onComplete?.Invoke(null, resp.UserMessage ?? resp.error ?? "baas bootstrap failed");
                    return;
                }
                var bootstrap = JsonUtility.FromJson<BaasBootstrapResponse>(raw);
                if (bootstrap == null || !bootstrap.ok)
                {
                    onComplete?.Invoke(bootstrap, bootstrap?.error ?? "baas bootstrap failed");
                    return;
                }
                ServiceId = bootstrap.service_id;
                PublicApiBase = bootstrap.public_api_base;
                Debug.Log("[BaasNetwork] base=" + PublicApiBase + " service=" + ServiceId);
                onComplete?.Invoke(bootstrap, null);
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
