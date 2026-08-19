using System;
using System.Collections.Generic;

namespace MAClient.Network.Baas
{
    [Serializable]
    public class BaasApiResponse<T>
    {
        public bool ok;
        public T data;
        public string error_code;
        public string error;
        public string details_json;
        public string raw_body;

        public bool IsSuccess => ok;

        public string ResolvedErrorCode =>
            string.IsNullOrEmpty(error_code) ? BaasErrorCatalog.ResolveCode(error ?? string.Empty) : error_code;

        public string UserMessage =>
            string.IsNullOrEmpty(error) ? BaasErrorCatalog.MessageZh(ResolvedErrorCode) : error;

        public static BaasApiResponse<T> FromJson(string json, Func<string, T> parseData)
        {
            var resp = new BaasApiResponse<T> { raw_body = json ?? string.Empty };
            if (string.IsNullOrEmpty(json))
            {
                resp.ok = false;
                resp.error_code = BaasErrorCodes.BAAS_JSON_PARSE_FAILED;
                resp.error = BaasErrorCatalog.MessageZh(resp.error_code);
                return resp;
            }
            resp.ok = ExtractBool(json, "ok");
            resp.error_code = ExtractString(json, "error_code");
            if (string.IsNullOrEmpty(resp.error_code))
                resp.error_code = BaasErrorCatalog.ResolveCode(ExtractString(json, "error"));
            resp.error = ExtractString(json, "error");
            if (string.IsNullOrEmpty(resp.error) && !resp.ok)
                resp.error = BaasErrorCatalog.MessageZh(resp.ResolvedErrorCode);
            resp.details_json = ExtractObject(json, "details");
            if (resp.ok && parseData != null)
            {
                var dataJson = ExtractObject(json, "data");
                if (!string.IsNullOrEmpty(dataJson))
                    resp.data = parseData(dataJson);
                else if (typeof(T) == typeof(string))
                    resp.data = (T)(object)json;
            }
            return resp;
        }

        public static BaasApiResponse<string> FromRawJson(string json)
        {
            return BaasApiResponse<string>.FromJson(json, ParseStringFragment);
        }

        static string ParseStringFragment(string raw) => raw ?? string.Empty;

        static bool ExtractBool(string json, string key)
        {
            var marker = "\"" + key + "\":";
            int idx = json.IndexOf(marker, StringComparison.Ordinal);
            if (idx < 0) return false;
            idx += marker.Length;
            while (idx < json.Length && char.IsWhiteSpace(json[idx])) idx++;
            if (idx + 4 <= json.Length && json.Substring(idx, 4) == "true") return true;
            return false;
        }

        public static string ExtractString(string json, string key)
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
                int end = idx + 1;
                while (end < json.Length)
                {
                    if (json[end] == '"' && json[end - 1] != '\\') break;
                    end++;
                }
                return end > idx + 1 ? json.Substring(idx + 1, end - idx - 1) : string.Empty;
            }
            int endNum = idx;
            while (endNum < json.Length && (char.IsDigit(json[endNum]) || json[endNum] == '-' || json[endNum] == '.'))
                endNum++;
            return endNum > idx ? json.Substring(idx, endNum - idx) : string.Empty;
        }

        public static int ExtractInt(string json, string key, int defaultValue = 0)
        {
            var raw = ExtractString(json, key);
            return int.TryParse(raw, out var value) ? value : defaultValue;
        }

        public static string ExtractObject(string json, string key)
        {
            var marker = "\"" + key + "\":";
            int idx = json.IndexOf(marker, StringComparison.Ordinal);
            if (idx < 0) return string.Empty;
            idx += marker.Length;
            while (idx < json.Length && char.IsWhiteSpace(json[idx])) idx++;
            if (idx >= json.Length) return string.Empty;
            char open = json[idx];
            if (open != '{' && open != '[') return string.Empty;
            char close = open == '{' ? '}' : ']';
            int depth = 0;
            for (int i = idx; i < json.Length; i++)
            {
                if (json[i] == open) depth++;
                else if (json[i] == close)
                {
                    depth--;
                    if (depth == 0) return json.Substring(idx, i - idx + 1);
                }
            }
            return string.Empty;
        }
    }
}
