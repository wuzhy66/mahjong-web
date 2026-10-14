<script setup lang="ts">
defineProps<{rule?: {id: string; name: string; description: string}}>()
const emit = defineEmits<{close: []}>()
</script>

<template>
  <aside id="rules-help" class="rules-panel" role="dialog" :aria-label="(rule?.name ?? '杭州麻将') + '玩法说明'">
    <header class="rules-heading"><h2>{{ rule?.name ?? '杭州麻将' }}怎么玩？</h2><button class="quiet" aria-label="关闭玩法说明" @click="emit('close')">关闭</button></header>
    <div class="rules-body">
      <template v-if="!rule || rule.id === 'hangzhou'">
        <section><h3>本桌的特殊规则</h3>
          <p><strong>白板是财神</strong>，能代替其他牌组成牌型；白板不能吃、碰、杠，可以打出。红中、发财和风牌都是普通字牌。</p>
          <p>无花牌，牌墙保留最后 <strong>20 张</strong>；可摸牌用完且无人胡牌就是流局。</p>
        </section>
        <section><h3>怎么胡牌</h3>
          <p><strong>只能自摸</strong>：自己摸到牌后成胡，才会出现「胡牌」。不能胡别人打出的牌，也不能抢杠胡。</p>
          <p>没有任何吃碰杠时，也可以胡 <strong>七对子</strong>；四张相同的牌可以算两个对子。持有白板仍可普通自摸，不强制要求爆头或杠开。</p>
        </section>
        <section><h3>吃、碰、杠怎么选</h3>
          <ul>
            <li><strong>吃：</strong>只能吃上家的牌，一局最多两摊吃。按钮中金色高亮的中文牌名，就是要吃进来的牌。</li>
            <li><strong>杠：</strong>杠后从牌墙尾部补摸一张；可摸张数为 0 时不能再杠。</li>
          </ul>
          <p><strong>碰、明杠优先于吃</strong>。只有当前合法的动作才会显示按钮，点「过」就是放弃这次响应。</p>
        </section>
        <section><h3>打白板后的「抓打圈」</h3>
          <p>有人打出白板，会进入抓打圈。其余玩家这一圈<strong>只能打出刚摸到的牌</strong>，不能吃、碰、明杠或补杠；仍可自摸或暗杠。</p>
          <p>打出白板的人不受上述限制。轮次回到发起者时解除；发起者若在圈内吃碰后打出普通牌，也会解除。</p>
        </section>
        <section><h3>谁坐庄，怎么结算</h3>
          <p><strong>谁胡牌，下一局谁坐庄；流局由原庄家连庄。</strong>本桌底分为 1，庄家参与的支付按 8 倍计算：</p>
          <div class="score-examples">
            <div><strong>庄家胡 1 番</strong><span>三位闲家各付 8 分，庄家得 <b>24 分</b>。</span></div>
            <div><strong>闲家胡 1 番</strong><span>庄家付 8 分，另两位闲家各付 1 分，赢家得 <b>10 分</b>。</span></div>
          </div>
          <p>2 番时，上述分数全部乘 2，其他番数以此类推。流局四家本局都是 0 分，累计积分保留。</p>
        </section>
        <details><summary>展开加番说明：七对、爆头、财飘与杠</summary>
          <p>平胡为 1 番，七对为 2 番；七对中的豪华、双豪华、三豪华分别为 4、8、16 番。豪华组按实际相同的四张牌计算，不能用白板代牌凑出一组豪华。</p>
          <p><strong>爆头：</strong>打完牌后，下一摸不论什么牌都能胡；爆头胡牌再乘 2。</p>
          <p><strong>财飘：</strong>在爆头状态下打出白板，会记一次财飘。普通打白板只触发抓打圈，不一定加番。</p>
          <p><strong>连续动作链：</strong>每次财飘或杠乘 2，最多计 6 次；打普通牌或非财飘的白板会清空链。吃碰通常也会断链，抓打圈发起者吃碰可保留旧链。</p>
          <p>胡牌时「手里白板＋当前链内飘出的白板」恰好为 4 张，再乘 2，可以与爆头叠加。最终番数和加番项会显示在结算中。</p>
        </details>
        <section><h3>网页上怎么操作</h3>
          <p>点击手牌选中，再点「出牌」；也可以再次点击已选中的同一张牌出牌。吃碰杠胡都要由你点击确认。</p>
          <p>「AI 提示」给出当前合法动作的概率，并选中推荐出牌，<strong>不会替你执行动作</strong>。牌桌可滚轮缩放、按住左键拖动；一局结束后可明牌逐步复盘，再开始下一局。</p>
        </section>
      </template>
      <template v-else><p>{{ rule.description }}</p><p>点击手牌选中后出牌，吃碰杠胡按当前显示的合法动作操作。</p></template>
    </div>
  </aside>
</template>

<style scoped>
.rules-panel{position:fixed;right:16px;top:82px;width:min(560px,calc(100vw - 32px));max-height:calc(100dvh - 100px);padding:0;display:flex;flex-direction:column}
.rules-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px;border-bottom:1px solid #ffffff18;flex-shrink:0}
.rules-heading h2{margin:0;font-size:20px;line-height:1.4}
.rules-heading button{flex-shrink:0;color:var(--gold)}
.rules-body{padding:0 20px 18px;overflow-y:auto;overscroll-behavior:contain;min-height:0;font-size:13px;line-height:1.8}
.rules-body section{padding-top:18px}
.rules-body h3{margin:0 0 8px;font-size:15px;color:var(--gold)}
.rules-body p{margin:8px 0;color:#d4dfd3}
.rules-body strong{color:#fff2cf}
.rules-body ul{padding-left:20px;margin:8px 0}
.rules-body li{margin:8px 0;color:#d4dfd3}
.score-examples{display:grid;gap:8px;margin:12px 0}
.score-examples>div{display:grid;gap:3px;background:#ffffff08;border:1px solid #ffffff12;border-radius:8px;padding:10px 12px}
.score-examples b{color:var(--gold)}
.rules-body details{margin-top:18px;border:1px solid #d9be8338;border-radius:8px;padding:10px 12px}
.rules-body summary{cursor:pointer;color:var(--gold);font-weight:600}
@media(max-width:760px){.rules-panel{top:68px;max-height:calc(100dvh - 84px)}.rules-heading{padding:12px 16px}.rules-body{padding:0 16px 16px}.rules-heading h2{font-size:18px}}
</style>
