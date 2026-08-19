using System;
using System.Collections.Generic;

namespace MAClient.Network.Baas
{
    /// <summary>Shared runtime context after bootstrap + optional guest login.</summary>
    public sealed class BaasClientContext
    {
        public string PortalBaseUrl { get; internal set; }
        public string ServiceId { get; internal set; }
        public string ApiKey { get; internal set; }
        public string PublicApiBase { get; internal set; }
        public string PlayerId { get; internal set; }
        public string PlayerToken { get; internal set; }
        public BaasEndpointRegistry Endpoints { get; } = new BaasEndpointRegistry();

        public string ApiPrefix => (PortalBaseUrl ?? string.Empty).TrimEnd('/') + (PublicApiBase ?? string.Empty);

        public Dictionary<string, string> ServiceHeaders()
        {
            return new Dictionary<string, string>
            {
                ["X-Baas-Api-Key"] = ApiKey ?? string.Empty,
                ["X-Baas-Service-Id"] = ServiceId ?? string.Empty,
            };
        }

        public Dictionary<string, string> PlayerHeaders()
        {
            var headers = ServiceHeaders();
            headers["Authorization"] = "Bearer " + (PlayerToken ?? string.Empty);
            headers["X-Baas-Player-Id"] = PlayerId ?? string.Empty;
            return headers;
        }

        public void SetSession(string playerToken, string playerId)
        {
            PlayerToken = playerToken ?? string.Empty;
            PlayerId = playerId ?? string.Empty;
        }

        public string ResolveEndpoint(string key, string fallbackRelative = "")
        {
            return Endpoints.Resolve(PortalBaseUrl, key, ServiceId, fallbackRelative);
        }
    }

    public sealed class BaasEndpointRegistry
    {
        readonly Dictionary<string, string> _paths = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        public void LoadFromBootstrapJson(string bootstrapJson, string serviceId)
        {
            _paths.Clear();
            var endpointsObj = BaasApiResponse<string>.ExtractObject(bootstrapJson, "endpoints");
            if (string.IsNullOrEmpty(endpointsObj)) return;
            ParseFlatObject(endpointsObj, serviceId);
        }

        void ParseFlatObject(string json, string serviceId)
        {
            int i = 0;
            while (i < json.Length)
            {
                int keyStart = json.IndexOf('"', i);
                if (keyStart < 0) break;
                int keyEnd = json.IndexOf('"', keyStart + 1);
                if (keyEnd < 0) break;
                var key = json.Substring(keyStart + 1, keyEnd - keyStart - 1);
                int valStart = json.IndexOf('"', keyEnd + 1);
                if (valStart < 0) break;
                int valEnd = json.IndexOf('"', valStart + 1);
                if (valEnd < 0) break;
                var val = json.Substring(valStart + 1, valEnd - valStart - 1);
                val = val.Replace("{service_id}", serviceId ?? string.Empty);
                _paths[key] = val;
                i = valEnd + 1;
            }
        }

        public string Resolve(string portalBase, string key, string serviceId, string fallbackRelative)
        {
            if (_paths.TryGetValue(key, out var path) && !string.IsNullOrEmpty(path))
                return (portalBase ?? string.Empty).TrimEnd('/') + path;
            var rel = fallbackRelative ?? string.Empty;
            if (!rel.StartsWith("/")) rel = "/api/baas/v1/" + serviceId + rel;
            return (portalBase ?? string.Empty).TrimEnd('/') + rel;
        }
    }
}
