using System;
using System.Collections.Generic;

namespace MAClient.Network.Baas
{
    /// <summary>
    /// 从 bootstrap JSON 解析的功能开关集合。
    /// 未出现在 bootstrap 中的功能默认视为<strong>已启用</strong>（兼容旧服务端）。
    /// </summary>
    public sealed class BaasFeatureFlags
    {
        readonly Dictionary<string, bool> _flags = new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase);

        /// <summary>功能是否已开通。未知键返回 true。</summary>
        public bool IsEnabled(string featureKey)
        {
            if (string.IsNullOrWhiteSpace(featureKey)) return false;
            return !_flags.TryGetValue(featureKey, out var enabled) || enabled;
        }

        /// <summary>从 bootstrap 响应 JSON 加载 feature_flags 对象。</summary>
        public void LoadFromBootstrapJson(string bootstrapJson)
        {
            _flags.Clear();
            var obj = BaasApiResponse<string>.ExtractObject(bootstrapJson ?? string.Empty, "feature_flags");
            if (string.IsNullOrEmpty(obj)) return;
            ParseBoolObject(obj);
        }

        void ParseBoolObject(string json)
        {
            int i = 0;
            while (i < json.Length)
            {
                int keyStart = json.IndexOf('"', i);
                if (keyStart < 0) break;
                int keyEnd = json.IndexOf('"', keyStart + 1);
                if (keyEnd < 0) break;
                var key = json.Substring(keyStart + 1, keyEnd - keyStart - 1);
                int valStart = keyEnd + 1;
                while (valStart < json.Length && (char.IsWhiteSpace(json[valStart]) || json[valStart] == ':')) valStart++;
                if (valStart >= json.Length) break;
                bool enabled = json[valStart] == 't'; // true
                _flags[key] = enabled;
                i = valStart + 1;
            }
        }

        public IReadOnlyDictionary<string, bool> Snapshot() => _flags;
    }
}
