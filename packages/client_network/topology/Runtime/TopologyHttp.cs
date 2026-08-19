using System;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace MAClient.Network.Topology
{
    internal static class TopologyHttp
    {
        public static async Task<string> GetAsync(string url, int timeoutSeconds = 30)
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
    }
}
