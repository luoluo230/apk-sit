// Shared HTTP GET for Portal bootstrap calls (Unity + Editor).
// Copy with client_network topology/baas Runtime folders.

using System;
using System.Threading.Tasks;

#if UNITY_2018_1_OR_NEWER
using UnityEngine;
using UnityEngine.Networking;
#endif

namespace Game.Network.Common
{
    public static class PortalHttp
    {
        public static Task<string> GetAsync(string url, int timeoutSeconds = 30)
        {
#if UNITY_2018_1_OR_NEWER
            return GetUnityAsync(url, timeoutSeconds);
#else
            return Task.FromException<string>(new NotImplementedException("Define UNITY_2018_1_OR_NEWER or wire HttpClient"));
#endif
        }

#if UNITY_2018_1_OR_NEWER
        static async Task<string> GetUnityAsync(string url, int timeoutSeconds)
        {
            using (var req = UnityWebRequest.Get(url))
            {
                req.timeout = Math.Max(5, timeoutSeconds);
                var op = req.SendWebRequest();
                while (!op.isDone)
                    await Task.Yield();
#if UNITY_2020_1_OR_NEWER
                if (req.result != UnityWebRequest.Result.Success)
                    throw new InvalidOperationException("HTTP GET failed: " + req.error);
#else
                if (req.isNetworkError || req.isHttpError)
                    throw new InvalidOperationException("HTTP GET failed: " + req.error);
#endif
                return req.downloadHandler.text;
            }
        }
#endif
    }
}
