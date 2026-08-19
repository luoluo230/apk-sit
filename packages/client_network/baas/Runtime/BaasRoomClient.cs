using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace Baas.Client
{
    /// <summary>
    /// Fast integration client for casual room + battle REST APIs.
    /// </summary>
    public sealed class BaasRoomClient
    {
        readonly string _baseUrl;
        readonly string _serviceId;
        readonly string _apiKey;
        readonly string _playerToken;
        readonly string _playerId;

        public BaasRoomClient(string baseUrl, string serviceId, string apiKey, string playerToken, string playerId)
        {
            _baseUrl = (baseUrl ?? string.Empty).TrimEnd('/');
            _serviceId = serviceId ?? string.Empty;
            _apiKey = apiKey ?? string.Empty;
            _playerToken = playerToken ?? string.Empty;
            _playerId = playerId ?? string.Empty;
        }

        public IEnumerator MatchmakeAsync(string envKey, string battleMode, Action<string, string> onComplete)
        {
            string url = $"{_baseUrl}/api/baas/v1/{_serviceId}/pvp/matchmake";
            var body = $"{{\"env_key\":\"{envKey}\",\"battle_mode\":\"{battleMode}\"}}";
            yield return PostJsonAsync(url, body, onComplete);
        }

        public IEnumerator SyncStateAsync(string roomId, string stateJson, Action<string, string> onComplete)
        {
            string url = $"{_baseUrl}/api/baas/v1/{_serviceId}/pvp/rooms/{roomId}/state";
            var body = $"{{\"state\":{stateJson}}}";
            yield return PostJsonAsync(url, body, onComplete);
        }

        public IEnumerator StartBattleAsync(string roomId, Action<string, string> onComplete)
        {
            string url = $"{_baseUrl}/api/baas/v1/{_serviceId}/rooms/{roomId}/start-battle";
            yield return PostJsonAsync(url, "{}", onComplete);
        }

        IEnumerator PostJsonAsync(string url, string jsonBody, Action<string, string> onComplete)
        {
            using (var request = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
            {
                byte[] payload = Encoding.UTF8.GetBytes(jsonBody ?? "{}");
                request.uploadHandler = new UploadHandlerRaw(payload);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                request.SetRequestHeader("X-Baas-Api-Key", _apiKey);
                request.SetRequestHeader("X-Baas-Service-Id", _serviceId);
                request.SetRequestHeader("Authorization", "Bearer " + _playerToken);
                request.SetRequestHeader("X-Baas-Player-Id", _playerId);
                request.timeout = 15;
                yield return request.SendWebRequest();
                if (request.result != UnityWebRequest.Result.Success)
                {
                    onComplete?.Invoke(null, request.error ?? "request failed");
                    yield break;
                }
                onComplete?.Invoke(request.downloadHandler.text, null);
            }
        }
    }
}
