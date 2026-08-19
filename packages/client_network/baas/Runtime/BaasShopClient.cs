using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>商城与钱包客户端。</summary>
    public sealed class BaasShopClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;

        public BaasShopClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        /// <summary>GET 商品目录。</summary>
        public IEnumerator GetCatalogAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/shop/catalog", _ctx.ServiceHeaders(), onComplete);
        }

        /// <summary>GET 钱包余额。</summary>
        public IEnumerator GetWalletAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/shop/wallet", _ctx.PlayerHeaders(), onComplete);
        }

        /// <summary>POST 购买商品。</summary>
        public IEnumerator PurchaseAsync(string productId, Action<BaasApiResponse<string>> onComplete)
        {
            var body = BaasJsonBody.Object(("product_id", productId ?? string.Empty));
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/shop/purchase", body, _ctx.PlayerHeaders(), onComplete);
        }
    }
}
