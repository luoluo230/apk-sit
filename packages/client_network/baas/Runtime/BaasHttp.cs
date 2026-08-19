using System;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace MAClient.Network.Baas
{
    public delegate void BaasHttpHook(BaasHttpContext context);

    public sealed class BaasHttpContext
    {
        public string Url;
        public string Method;
        public string RequestBody;
        public Dictionary<string, string> Headers;
        public long StatusCode;
        public string ResponseBody;
        public string TransportError;
        public BaasApiResponse<string> Parsed;
    }

    public static class BaasRequestPipeline
    {
        static readonly List<BaasHttpHook> _before = new List<BaasHttpHook>();
        static readonly List<BaasHttpHook> _after = new List<BaasHttpHook>();

        public static void RegisterBefore(BaasHttpHook hook)
        {
            if (hook != null && !_before.Contains(hook)) _before.Add(hook);
        }

        public static void RegisterAfter(BaasHttpHook hook)
        {
            if (hook != null && !_after.Contains(hook)) _after.Add(hook);
        }

        internal static void RunBefore(BaasHttpContext ctx)
        {
            foreach (var hook in _before) hook?.Invoke(ctx);
        }

        internal static void RunAfter(BaasHttpContext ctx)
        {
            foreach (var hook in _after) hook?.Invoke(ctx);
        }
    }

    internal static class BaasHttp
    {
        public static IEnumeratorRequest PostJson(string url, string jsonBody, Dictionary<string, string> headers, Action<BaasApiResponse<string>> onComplete, int timeoutSeconds = 20)
        {
            var ctx = new BaasHttpContext { Url = url, Method = "POST", RequestBody = jsonBody, Headers = headers };
            BaasRequestPipeline.RunBefore(ctx);
            return new JsonRequest(ctx, BuildPost(url, jsonBody, headers, timeoutSeconds), onComplete);
        }

        public static IEnumeratorRequest Get(string url, Dictionary<string, string> headers, Action<BaasApiResponse<string>> onComplete, int timeoutSeconds = 30)
        {
            var ctx = new BaasHttpContext { Url = url, Method = "GET", Headers = headers };
            BaasRequestPipeline.RunBefore(ctx);
            return new JsonRequest(ctx, BuildGet(url, headers, timeoutSeconds), onComplete);
        }

        internal abstract class IEnumeratorRequest : System.Collections.IEnumerator
        {
            readonly UnityWebRequest _request;
            readonly Action<BaasApiResponse<string>> _onComplete;
            readonly BaasHttpContext _ctx;
            bool _done;

            protected IEnumeratorRequest(UnityWebRequest request, BaasHttpContext ctx, Action<BaasApiResponse<string>> onComplete)
            {
                _request = request;
                _ctx = ctx;
                _onComplete = onComplete;
            }

            public object Current => _request.isDone ? null : _request;

            public bool MoveNext()
            {
                if (_done) return false;
                if (!_request.isDone) return true;
                _done = true;
                Complete();
                _request.Dispose();
                return false;
            }

            void Complete()
            {
                _ctx.StatusCode = _request.responseCode;
                _ctx.ResponseBody = _request.downloadHandler != null ? _request.downloadHandler.text : string.Empty;
#if UNITY_2020_1_OR_NEWER
                var transportFail = _request.result != UnityWebRequest.Result.Success;
#else
                var transportFail = _request.isNetworkError || _request.isHttpError;
#endif
                if (transportFail && string.IsNullOrEmpty(_ctx.ResponseBody))
                {
                    _ctx.TransportError = _request.error ?? "request failed";
                    var fail = new BaasApiResponse<string>
                    {
                        ok = false,
                        error_code = BaasErrorCodes.BAAS_UNKNOWN,
                        error = _ctx.TransportError,
                    };
                    _ctx.Parsed = fail;
                    BaasRequestPipeline.RunAfter(_ctx);
                    _onComplete?.Invoke(fail);
                    return;
                }
                var parsed = BaasApiResponse<string>.FromRawJson(_ctx.ResponseBody);
                parsed.raw_body = _ctx.ResponseBody;
                if (!parsed.ok && string.IsNullOrEmpty(parsed.error_code))
                    parsed.error_code = BaasErrorCatalog.ResolveCode(parsed.error);
                _ctx.Parsed = parsed;
                BaasRequestPipeline.RunAfter(_ctx);
                _onComplete?.Invoke(parsed);
            }

            public void Reset() { }
        }

        sealed class JsonRequest : IEnumeratorRequest
        {
            public JsonRequest(BaasHttpContext ctx, UnityWebRequest request, Action<BaasApiResponse<string>> onComplete)
                : base(request, ctx, onComplete) { }
        }

        static UnityWebRequest BuildPost(string url, string jsonBody, Dictionary<string, string> headers, int timeoutSeconds)
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

        static UnityWebRequest BuildGet(string url, Dictionary<string, string> headers, int timeoutSeconds)
        {
            var request = UnityWebRequest.Get(url);
            request.downloadHandler = new DownloadHandlerBuffer();
            ApplyHeaders(request, headers);
            request.timeout = Math.Max(5, timeoutSeconds);
            request.SendWebRequest();
            return request;
        }

        static void ApplyHeaders(UnityWebRequest request, Dictionary<string, string> headers)
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
