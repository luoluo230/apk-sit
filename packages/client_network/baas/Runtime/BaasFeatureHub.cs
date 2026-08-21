using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>
    /// BaaS 功能客户端统一入口。
    /// <para>用法：Bootstrap 完成并取得 <see cref="BaasClientContext"/> 后，通过本类获取各业务模块客户端。</para>
    /// <para>未开通的功能在调用对应属性时会抛出 <see cref="InvalidOperationException"/>（可通过 <see cref="IsEnabled"/> 预先判断）。</para>
    /// </summary>
    public sealed class BaasFeatureHub
    {
        readonly BaasClientContext _ctx;

        public BaasFeatureHub(BaasClientContext ctx)
        {
            _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx));
        }

        /// <summary>当前会话上下文（含 ServiceId、PlayerToken、Endpoints）。</summary>
        public BaasClientContext Context => _ctx;

        /// <summary>功能是否已在 bootstrap 中开通。</summary>
        public bool IsEnabled(string featureKey) => _ctx.FeatureFlags.IsEnabled(featureKey);

        /// <summary>账号：游客/密码登录、注册。</summary>
        public BaasAuthClient Auth => Require(BaasFeatureKeys.Login, () => new BaasAuthClient(_ctx));

        /// <summary>公告：拉取有效公告列表。</summary>
        public BaasAnnounceClient Announce => Require(BaasFeatureKeys.Announce, () => new BaasAnnounceClient(_ctx));

        /// <summary>邮件：收件箱查询与附件领取。</summary>
        public BaasMailClient Mail => Require(BaasFeatureKeys.Mail, () => new BaasMailClient(_ctx));

        /// <summary>云存档：玩家 KV 读写。</summary>
        public BaasCloudSaveClient CloudSave => Require(BaasFeatureKeys.CloudSave, () => new BaasCloudSaveClient(_ctx));

        /// <summary>排行榜：提交分数与查询榜单。</summary>
        public BaasLeaderboardClient Leaderboard => Require(BaasFeatureKeys.Leaderboard, () => new BaasLeaderboardClient(_ctx));

        /// <summary>商城/钱包：商品列表、购买、余额查询。</summary>
        public BaasShopClient Shop => Require(BaasFeatureKeys.Economy, () => new BaasShopClient(_ctx));

        /// <summary>成就：列表、进度上报、奖励领取。</summary>
        public BaasAchievementClient Achievement => Require(BaasFeatureKeys.Achievement, () => new BaasAchievementClient(_ctx));

        /// <summary>礼包码：兑换奖励。</summary>
        public BaasGiftClient Gift => Require(BaasFeatureKeys.Gift, () => new BaasGiftClient(_ctx));

        /// <summary>公会：创建、查询、加入。</summary>
        public BaasGuildClient Guild => Require(BaasFeatureKeys.Guild, () => new BaasGuildClient(_ctx));

        /// <summary>战令：赛季状态、经验、等级奖励。</summary>
        public BaasBattlePassClient BattlePass => Require(BaasFeatureKeys.BattlePass, () => new BaasBattlePassClient(_ctx));

        /// <summary>周期任务：日/周任务列表、进度、领取。</summary>
        public BaasTaskClient Task => Require(BaasFeatureKeys.PeriodicTask, () => new BaasTaskClient(_ctx));

        /// <summary>防沉迷：会话上报、心跳、实名信息。</summary>
        public BaasComplianceClient Compliance => Require(BaasFeatureKeys.Compliance, () => new BaasComplianceClient(_ctx));

        /// <summary>PVE 推图：体力、进度、开战/结算（含 checksum 与 replay_hash）。</summary>
        public BaasPveClient Pve => Require(BaasFeatureKeys.Pve, () => new BaasPveClient(_ctx));

        /// <summary>异步竞技场：对手列表、防守阵容、离线对战结算。</summary>
        public BaasArenaClient Arena => Require(BaasFeatureKeys.Arena, () => new BaasArenaClient(_ctx));

        /// <summary>英雄：背包、升级、装备。</summary>
        public BaasHeroClient Hero => Require(BaasFeatureKeys.Hero, () => new BaasHeroClient(_ctx));

        /// <summary>背包：道具/装备列表与消耗。</summary>
        public BaasInventoryClient Inventory => Require(BaasFeatureKeys.Inventory, () => new BaasInventoryClient(_ctx));

        /// <summary>抽卡：卡池、pity、召唤。</summary>
        public BaasGachaClient Gacha => Require(BaasFeatureKeys.Gacha, () => new BaasGachaClient(_ctx));

        /// <summary>挂机：离线收益查询与领取。</summary>
        public BaasIdleClient Idle => Require(BaasFeatureKeys.Idle, () => new BaasIdleClient(_ctx));

        /// <summary>爬塔：层数进度、开战、结算。</summary>
        public BaasTowerClient Tower => Require(BaasFeatureKeys.Tower, () => new BaasTowerClient(_ctx));

        /// <summary>内购：下单、验单、发钻石。</summary>
        public BaasIapClient Iap => Require(BaasFeatureKeys.Iap, () => new BaasIapClient(_ctx));

        /// <summary>实时房间 PVP：匹配、帧同步（AFK 类游戏通常不启用）。</summary>
        public BaasRoomClient Room => Require(BaasFeatureKeys.Pvp, () => new BaasRoomClient(_ctx));

        /// <summary>跳过功能门控，直接获取客户端（仅用于 bootstrap 前或单元测试）。</summary>
        public BaasAuthClient AuthUnchecked => new BaasAuthClient(_ctx);

        T Require<T>(string featureKey, Func<T> factory)
        {
            if (!_ctx.FeatureFlags.IsEnabled(featureKey))
                throw new InvalidOperationException($"BaaS 功能未开通: {featureKey}。请在管理台启用或在 bootstrap feature_flags 中打开。");
            return factory();
        }
    }
}
