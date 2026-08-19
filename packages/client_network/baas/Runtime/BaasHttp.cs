// Self-contained HTTP helper for BaaS client module (import with baas package only).

using System;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace MAClient.Network.Baas
{
    internal static class BaasHttp
    {
        public static IEnumeratorRequest PostJson(string url, string jsonBody, System.Collections.Generic.Dictionary<string, string> headers, Action<string, string> onComplete, int timeoutSeconds = 20)
        {
            return new PostJsonRequest(url, jsonBody, headers, onComplete, timeoutSeconds);
        }

        public static IEnumeratorRequest Get(string url, System.Collections.Generic.Dictionary<string, string> headers, Action<string, string> onComplete, int timeoutSeconds = 30)
        {
            return new GetRequest(url, headers, onComplete, timeoutSeconds);
        }

        internal abstract class IEnumeratorRequest : System.Collections.IEnumerator
        {
            readonly UnityWebRequest _request;
            readonly Action<string, string> _onComplete;
            bool _done;

            protected IEnumeratorRequest(UnityWebRequest request, Action<string, string> onComplete)
            {
                _request = request;
                _onComplete = onComplete;
            }

            public object Current => _request.isDone ? null : _request;

            public bool MoveNext()
            {
                if (_done) return false;
                if (!_request.isDone) return true;
                _done = true;
#if UNITY_2020_1_OR_NEWER
                if (_request.result != UnityWebRequest.Result.Success)
#else
                if (_request.isNetworkError || _request.isHttpError)
#endif
                {
                    _onComplete?.Invoke(null, _request.error ?? "request failed");
                }
                else
                {
                    _onComplete?.Invoke(_request.downloadHandler.text, null);
                }
                _request.Dispose();
                return false;
            }

            public void Reset() { }
        }

        sealed class PostJsonRequest : IEnumeratorRequest
        {
            public PostJsonRequest(string url, string jsonBody, System.Collections.Generic.Dictionary<string, string> headers, Action<string, string> onComplete, int timeoutSeconds)
                : base(Build(url, jsonBody, headers, timeoutSeconds), onComplete) { }

            static UnityWebRequest Build(string url, string jsonBody, System.Collections.Generic.Dictionary<string, string> headers, int timeoutSeconds)
            {
                var request = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST);
                byte[] payload = Encoding.UTF8.GetBytes(jsonBody ?? "{}");
                request.uploadHandler = new UploadHandlerRaw(payload);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                ApplyHeaders(request, headers);
                request.timeout = Math.Max(5, timeoutSeconds);
                request.SendWebRequest();
                return request;
            }
        }

        sealed class GetRequest : IEnumeratorRequest
        {
            public GetRequest(string url, System.Collections.Generic.Dictionary<string, string> headers, Action<string, string> onComplete, int timeoutSeconds)
                : base(Build(url, headers, timeoutSeconds), onComplete) { }

            static UnityWebRequest Build(string url, System.Collections.Generic.Dictionary<string, string> headers, int timeoutSeconds)
            {
                var request = UnityWebRequest.Get(url);
                ApplyHeaders(request, headers);
                request.timeout = Math.Max(5, timeoutSeconds);
                request.SendWebRequest();
                return request;
            }
        }

        static void ApplyHeaders(UnityWebRequest request, System.Collections.Generic.Dictionary<string, string> headers)
        {
            if (headers == null) return;
            foreach (var kv in headers)
            {
                if (!string.IsNullOrEmpty(kv.Key) && kv.Value != null)
                    request.SetRequestHeader(kv.Key, kv.Value);
            }
        }
    }
}
