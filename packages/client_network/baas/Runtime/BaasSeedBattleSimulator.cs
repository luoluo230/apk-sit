using System;
using System.Collections.Generic;
using System.Text;

namespace MAClient.Network.Baas
{
    /// <summary>
    /// 基于服务端 seed 的确定性战斗演算（与 BaaS 反作弊 replay_hash 公式对齐）。
    /// 用于 PVE 推图与异步竞技场客户端结算前的本地模拟。
    /// </summary>
    public static class BaasSeedBattleSimulator
    {
        static readonly Dictionary<int, int> HeroPower = new Dictionary<int, int>
        {
            { 1, 120 }, { 2, 150 }, { 3, 140 },
            { 11, 180 }, { 12, 130 },
            { 21, 160 }, { 22, 155 },
        };

        public sealed class SimResult
        {
            public bool Win;
            public int Stars;
            public int DurationMs;
            public int Ticks;
            public string TeamJson;
            public int AttackerPower;
            public int DefenderPower;
        }

        public static SimResult SimulatePve(int seed, int[] attackerHeroes)
        {
            return Simulate(seed, attackerHeroes, null);
        }

        public static SimResult SimulateArena(int seed, int[] attackerHeroes, int[] defenderHeroes)
        {
            return Simulate(seed, attackerHeroes, defenderHeroes ?? Array.Empty<int>());
        }

        public static string HeroesTeamJson(int[] heroes)
        {
            var sb = new StringBuilder("{\"heroes\":[");
            if (heroes != null)
            {
                for (int i = 0; i < heroes.Length; i++)
                {
                    if (i > 0) sb.Append(',');
                    sb.Append(heroes[i]);
                }
            }
            sb.Append("]}");
            return sb.ToString();
        }

        public static int SumHeroPower(int[] heroes)
        {
            var total = 0;
            if (heroes == null) return total;
            foreach (var hid in heroes)
            {
                if (HeroPower.TryGetValue(hid, out var p)) total += p;
                else total += 100;
            }
            return total;
        }

        static SimResult Simulate(int seed, int[] attackerHeroes, int[] defenderHeroes)
        {
            var rng = new Random(seed);
            var atkPower = SumHeroPower(attackerHeroes);
            var defPower = defenderHeroes == null
                ? Math.Max(80, atkPower / 2)
                : Math.Max(1, SumHeroPower(defenderHeroes));
            var atkHp = atkPower;
            var defHp = defPower;
            var ticks = 0;
            while (atkHp > 0 && defHp > 0 && ticks < 120)
            {
                defHp -= rng.Next(8, 28);
                if (defHp <= 0) break;
                atkHp -= rng.Next(4, 18);
                ticks++;
            }
            var win = defHp <= 0 && atkHp > 0;
            var stars = !win ? 0 : (ticks < 35 ? 3 : ticks < 70 ? 2 : 1);
            var durationMs = Math.Max(3000, ticks * 250);
            return new SimResult
            {
                Win = win,
                Stars = stars,
                DurationMs = durationMs,
                Ticks = ticks,
                TeamJson = HeroesTeamJson(attackerHeroes),
                AttackerPower = atkPower,
                DefenderPower = defPower,
            };
        }
    }
}
