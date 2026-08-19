using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>
    /// BaaS API 协程辅助：统一处理空响应、网络失败与业务错误，减少各业务模块重复判空。
    /// </summary>
    public static class BaasCoroutineHelper
    {
        /// <summary>
        /// 执行带回调的 API 协程，保证 onComplete 至少收到一次响应对象。
        /// </summary>
        public static IEnumerator Invoke(
            Func<Action<BaasApiResponse<string>>, IEnumerator> apiCall,
            Action<BaasApiResponse<string>> onComplete)
        {
            BaasApiResponse<string> resp = null;
            yield return apiCall(r => resp = r);
            onComplete?.Invoke(resp ?? Fail(BaasErrorCodes.BAAS_UNKNOWN, "网络无响应"));
        }

        /// <summary>判断响应是否成功，并输出 data 与中文错误信息。</summary>
        public static bool TryGetData(BaasApiResponse<string> resp, out string data, out string errorMessage)
        {
            data = resp?.data ?? string.Empty;
            if (resp != null && resp.ok)
            {
                errorMessage = null;
                return true;
            }
            errorMessage = resp?.UserMessage ?? BaasErrorCatalog.MessageZh(BaasErrorCodes.BAAS_UNKNOWN);
            return false;
        }

        /// <summary>构造本地失败响应（未发请求或协程中断时使用）。</summary>
        public static BaasApiResponse<string> Fail(string errorCode, string messageZh)
        {
            return new BaasApiResponse<string>
            {
                ok = false,
                error_code = errorCode ?? BaasErrorCodes.BAAS_UNKNOWN,
                error = string.IsNullOrEmpty(messageZh)
                    ? BaasErrorCatalog.MessageZh(errorCode)
                    : messageZh,
            };
        }
    }
}
