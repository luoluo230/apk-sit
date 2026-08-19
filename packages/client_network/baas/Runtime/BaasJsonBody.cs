using System;
using System.Text;

namespace MAClient.Network.Baas
{
    /// <summary>JSON 请求体构建辅助（轻量，无第三方依赖）。</summary>
    internal static class BaasJsonBody
    {
        public static string Object(params (string key, string value)[] fields)
        {
            var sb = new StringBuilder("{");
            for (int i = 0; i < fields.Length; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append('"').Append(Escape(fields[i].key)).Append("\":");
                sb.Append('"').Append(Escape(fields[i].value)).Append('"');
            }
            sb.Append('}');
            return sb.ToString();
        }

        public static string WithRaw(string key, string rawJsonFragment)
        {
            return "{\"" + Escape(key) + "\":" + (string.IsNullOrWhiteSpace(rawJsonFragment) ? "{}" : rawJsonFragment) + "}";
        }

        public static string Escape(string value) =>
            (value ?? string.Empty).Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}
