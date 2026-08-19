using System;
using System.Collections;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace MAClient.Network.Baas
{
    /// <summary>
    /// REST client for casual BaaS room + battle APIs. Pairs with casual_baas_server.
    /// </summary>
    public sealed class BaasRoomClient
    {
        readonly string _portalBase;
        readonly string _serviceId;
        readonly string _apiKey;
        string _playerToken;
        string _playerId;

        public BaasRoomClient(string portalBaseUrl, string serviceId, string apiKey, string playerToken = "", string playerId = "")
        {
            _portalBase = (portalBaseUrl ?? string.Empty).TrimEnd('/');
            _serviceId = serviceId ?? string.Empty;
            _apiKey = apiKey ?? string.Empty;
            _playerToken = playerToken ?? string.Empty;
            _playerId = playerId ?? string.Empty;
        }

        public string PlayerId => _playerId;
        public string PlayerToken => _playerToken;

        public void SetSession(string playerToken, string playerId)
        {
            _playerToken = playerToken ?? string.Empty;
            _playerId = playerId ?? string.Empty;
        }

        string ApiPrefix => _portalBase + "/api/baas/v1/" + _serviceId;

        Dictionary<string, string> ServiceHeaders()
        {
            return new Dictionary<string, string>
            {
                ["X-Baas-Api-Key"] = _apiKey,
                ["X-Baas-Service-Id"] = _serviceId,
            };
        }

        Dictionary<string, string> PlayerHeaders()
        {
            var headers = ServiceHeaders();
            headers["Authorization"] = "Bearer " + _playerToken;
            headers["X-Baas-Player-Id"] = _playerId;
            return headers;
        }

        public IEnumerator GuestLoginAsync(string displayName, Action<string, string> onComplete)
        {
            string url = ApiPrefix + "/auth/guest";
            var body = "{\"display_name\":\"" + EscapeJson(displayName) + "\"}";
            yield return BaasHttp.PostJson(url, body, ServiceHeaders(), (json, err) =>
            {
                if (!string.IsNullOrEmpty(err)) { onComplete?.Invoke(null, err); return; }
                var token = ExtractString(json, "token");
                var pid = ExtractString(json, "player_id");
                if (string.IsNullOrEmpty(token) || string.IsNullOrEmpty(pid))
                {
                    onComplete?.Invoke(null, "guest login parse failed");
                    return;
                }
                _playerToken = token;
                _playerId = pid;
                onComplete?.Invoke(json, null);
            });
        }

        public IEnumerator MatchmakeAsync(string battleMode, Action<string, string> onComplete)
        {
            string url = ApiPrefix + "/pvp/matchmake";
            var body = "{\"battle_mode\":\"" + EscapeJson(battleMode) + "\"}";
            yield return BaasHttp.PostJson(url, body, PlayerHeaders(), onComplete);
        }

        public IEnumerator StartBattleAsync(string roomId, Action<string, string> onComplete)
        {
            string url = ApiPrefix + "/rooms/" + Uri.EscapeDataString(roomId) + "/start-battle";
            yield return BaasHttp.PostJson(url, "{}", PlayerHeaders(), onComplete);
        }

        public IEnumerator SyncStateAsync(string roomId, string stateJson, Action<string, string> onComplete)
        {
            string url = ApiPrefix + "/pvp/rooms/" + Uri.EscapeDataString(roomId) + "/state";
            var body = "{\"state\":" + (string.IsNullOrWhiteSpace(stateJson) ? "{}" : stateJson) + "}";
            yield return BaasHttp.PostJson(url, body, PlayerHeaders(), onComplete);
        }

        public IEnumerator PushFrameAsync(string roomId, string frameJson, Action<string, string> onComplete)
        {
            string url = ApiPrefix + "/rooms/" + Uri.EscapeDataString(roomId) + "/frames";
            var body = "{\"frame\":" + (string.IsNullOrWhiteSpace(frameJson) ? "{}" : frameJson) + "}";
            yield return BaasHttp.PostJson(url, body, PlayerHeaders(), onComplete);
        }

        public IEnumerator PollFramesAsync(string roomId, int sinceSeq, int waitMs, Action<string, string> onComplete)
        {
            string url = ApiPrefix + "/rooms/" + Uri.EscapeDataString(roomId)
                + "/frames?since_seq=" + sinceSeq + "&wait_ms=" + Math.Max(0, waitMs);
            var headers = ServiceHeaders();
            headers["X-Baas-Player-Id"] = _playerId;
            yield return BaasHttp.Get(url, headers, onComplete, Math.Max(10, waitMs / 1000 + 5));
        }

        public IEnumerator FinishBattleAsync(string roomId, string resultJson, Action<string, string> onComplete)
        {
            string url = ApiPrefix + "/rooms/" + Uri.EscapeDataString(roomId) + "/finish-battle";
            var body = "{\"result\":" + (string.IsNullOrWhiteSpace(resultJson) ? "{}" : resultJson) + "}";
            yield return BaasHttp.PostJson(url, body, PlayerHeaders(), onComplete);
        }

        static string EscapeJson(string value)
        {
            return (value ?? string.Empty).Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        static string ExtractString(string json, string key)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(key)) return string.Empty;
            var marker = "\"" + key + "\":";
            int idx = json.IndexOf(marker, StringComparison.Ordinal);
            if (idx < 0) return string.Empty;
            idx += marker.Length;
            while (idx < json.Length && char.IsWhiteSpace(json[idx])) idx++;
            if (idx >= json.Length) return string.Empty;
            if (json[idx] == '"')
            {
                int end = json.IndexOf('"', idx + 1);
                return end > idx ? json.Substring(idx + 1, end - idx - 1) : string.Empty;
            }
            return string.Empty;
        }
    }
}
