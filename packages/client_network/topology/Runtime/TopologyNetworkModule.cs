// Topology client network module — pairs with topology_server.
// Copy Runtime/ + ../common/Runtime/PortalHttp.cs to Unity project.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Game.Network.Common;
using UnityEngine;

namespace Game.Network.Topology
{
    [Serializable]
    public class NetworkProfile
    {
        public string gateway_ws;
        public string login_http;
        public string game_ws;
        public string ops_http;
    }

    [Serializable]
    public class RuntimeBootstrapResponse
    {
        public bool ok;
        public string framework;
        public string client_module;
        public string bootstrap_kind;
        public NetworkProfile network_profile;
    }

    /// <summary>
    /// Fetches client-bootstrap and applies WebSocket gateway endpoints.
    /// </summary>
    public static class TopologyNetworkModule
    {
        public const string DefaultBootstrapPath = "/api/public/client-bootstrap";

        public static async Task<NetworkProfile> BootstrapAsync(
            string portalBaseUrl,
            string gameId,
            string gameKey,
            string envKey,
            string channel,
            string platform)
        {
            var qs = new Dictionary<string, string>
            {
                ["game_id"] = gameId,
                ["game_key"] = gameKey,
                ["env_key"] = envKey,
                ["channel"] = channel,
                ["platform"] = platform,
            };
            var url = portalBaseUrl.TrimEnd('/') + DefaultBootstrapPath + "?" + BuildQuery(qs);
            var json = await PortalHttp.GetAsync(url);
            var resp = JsonUtility.FromJson<RuntimeBootstrapResponse>(json);
            if (resp == null || !resp.ok || resp.network_profile == null)
                throw new InvalidOperationException("topology bootstrap failed");
            if (string.IsNullOrEmpty(resp.network_profile.gateway_ws))
                throw new InvalidOperationException("network_profile.gateway_ws required");
            Apply(resp.network_profile);
            return resp.network_profile;
        }

        public static void Apply(NetworkProfile profile)
        {
            Debug.Log("[TopologyNetwork] gateway=" + profile.gateway_ws);
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
