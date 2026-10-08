<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, qs } from '../../api'
import Modal from '../../components/Modal.vue'
import { useAuth } from '../../store'
import { SEMAFORO, SOPORTE, fecha, money, pct, toast, toastError } from '../../util'

const auth = useAuth()
const route = useRoute()
const vigencias = ref([])
const lotes = ref([])
const vig = ref('')
const lote = ref(route.query.lote ? Number(route.query.lote) : '')
const datos = ref(null)
const cotizaciones = ref([])
const q = ref('')
const filtro = ref('')
const sel = ref(null)
const ajuste = ref(null)

const vigencia = computed(() => vigencias.value.find((v) => v.id === vig.value))
const editable = computed(() => vigencia.value && vigencia.value.estado !== 'CERRADA')
const etiquetas = computed(() => cotizaciones.value.map((c) => c.etiqueta))
const filas = computed(() => (datos.value?.items || []).filter((i) => {
  if (q.value && !i.articulo.nombre.toLowerCase().includes(q.value.toLowerCase()) && !i.articulo.codigo_unspsc.startsWith(q.value)) return false
  if (filtro.value === 'alerta') return ['naranja', 'rojo'].includes(i.semaforo)
  if (filtro.value === 'atipico') return !!i.atipico_sugerido
  if (filtro.value) return i.soporte === filtro.value
  return true
}))

async function cargar() {
  if (!vig.value || !lote.value) return
  try {
    ;[datos.value, cotizaciones.value] = await Promise.all([
      api.get(`/analisis${qs({ vigencia_id: vig.value, lote_id: lote.value })}`),
      api.get(`/cotizaciones${qs({ vigencia_id: vig.value, lote_id: lote.value })}`)])
    if (sel.value) sel.value = datos.value.items.find((i) => i.articulo_id === sel.value.articulo_id)
  } catch (e) { toastError(e) }
}
onMounted(async () => {
  ;[vigencias.value, lotes.value] = await Promise.all([api.get('/vigencias'), api.get('/lotes')])
  vig.value = auth.vigencia?.id || vigencias.value[0]?.id || ''
  if (!lote.value) lote.value = lotes.value[0]?.id || ''
})
watch([vig, lote], cargar)

const precioDe = (i, et) => i.cotizaciones.find((c) => c.etiqueta === et)

async function excluir(c, excluido, motivo = '') {
  try {
    await api.post(`/cotizaciones/items/${c.item_id}/exclusion`, { excluido, motivo })
    await cargar()
  } catch (e) { toastError(e) }
}
function abrirAjuste(i) {
  ajuste.value = { metodo: i.metodo_manual ? i.metodo : '', precio_experto: i.precio_experto, justificacion: i.metodo_manual ? i.justificacion : '' }
}
async function guardarAjuste() {
  try {
    await api.put(`/analisis/${vig.value}/${sel.value.articulo_id}`, { ...ajuste.value, metodo: ajuste.value.metodo || null })
    toast('Análisis actualizado')
    ajuste.value = null
    cargar()
  } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>Análisis de precios</h1><div class="sub">Formato de análisis de precios y consolidación de bienes de características técnicas uniformes</div></div>
      <div class="row" v-if="vig && lote">
        <button class="btn ghost" @click="api.descargar(`/cotizaciones/zip${qs({ vigencia_id: vig, lote_id: lote })}`)">PDFs (ZIP)</button>
        <button class="btn" @click="api.descargar(`/analisis/exportar${qs({ vigencia_id: vig, lote_id: lote })}`)">Exportar formato Excel</button>
      </div>
    </div>
    <div class="row" style="margin-bottom:12px">
      <select v-model="vig"><option v-for="v in vigencias" :key="v.id" :value="v.id">Vigencia {{ v.codigo }} ({{ v.estado.toLowerCase() }})</option></select>
      <select v-model="lote"><option v-for="l in lotes" :key="l.id" :value="l.id">{{ l.numero }}. {{ l.nombre }}</option></select>
      <input v-model="q" placeholder="Buscar artículo…" class="grow" style="max-width:300px" />
      <select v-model="filtro">
        <option value="">Todos</option><option value="alerta">Dispersión en alerta</option><option value="atipico">Con atípico sugerido</option>
        <option v-for="(s, k) in SOPORTE" :key="k" :value="k">{{ s.label }}</option>
      </select>
    </div>
    <div v-if="datos" class="kpis">
      <div class="card kpi"><div class="l">Artículos</div><div class="v">{{ datos.resumen.total }}</div></div>
      <div v-for="(s, k) in SOPORTE" :key="k" class="card kpi" :style="{ borderColor: s.color }"><div class="l">{{ s.label }}</div><div class="v">{{ datos.resumen[k] || 0 }}</div></div>
    </div>
    <div v-if="cotizaciones.length" class="small muted" style="margin-bottom:8px">
      Cotizantes: <span v-for="c in cotizaciones" :key="c.id" style="margin-right:12px"><b>{{ c.etiqueta }}</b> = {{ c.proveedor.razon_social }} (<a :href="api.pdfUrl(c.id)" target="_blank" rel="noopener">PDF</a>)</span>
    </div>
    <div class="table-wrap tall">
      <table>
        <thead><tr>
          <th>Artículo</th><th v-for="e in etiquetas" :key="e" class="right">{{ e }}</th><th class="right">Hist. indexados</th>
          <th class="right">Disp. inicial</th><th>Método</th><th class="right">Precio estimado</th><th class="right">Disp. final</th><th>Soporte</th>
        </tr></thead>
        <tbody>
          <tr v-for="i in filas" :key="i.articulo_id" class="click" @click="sel = i">
            <td>{{ i.articulo.nombre }}<div class="small muted">{{ i.articulo.codigo_unspsc }} · {{ i.articulo.unidad }}</div></td>
            <td v-for="e in etiquetas" :key="e" class="right mono nowrap">
              <template v-if="precioDe(i, e)"><s v-if="precioDe(i, e).excluido" class="muted">{{ money(precioDe(i, e).precio) }}</s>
                <span v-else :style="precioDe(i, e).item_id === i.atipico_sugerido ? 'color:var(--rojo);font-weight:600' : ''">{{ money(precioDe(i, e).precio) }}</span></template>
            </td>
            <td class="right mono small">{{ i.historicos.map((h) => money(h.indexado)).join(' · ') || '—' }}</td>
            <td class="right">{{ pct(i.dispersion_inicial) }}</td>
            <td class="small">{{ i.metodo || '—' }}<span v-if="i.metodo_manual" title="Ajuste manual"> ✎</span></td>
            <td class="right mono"><b>{{ money(i.precio_estimado) }}</b></td>
            <td class="right nowrap"><span class="dot" :style="{ background: SEMAFORO[i.semaforo] }" />{{ pct(i.dispersion_final) }}</td>
            <td><span class="badge" :style="{ background: SOPORTE[i.soporte].color }">{{ SOPORTE[i.soporte].label }}</span></td>
          </tr>
          <tr v-if="datos && !filas.length"><td :colspan="7 + etiquetas.length" class="empty">Sin artículos</td></tr>
        </tbody>
      </table>
    </div>

    <Modal v-if="sel" :titulo="sel.articulo.nombre" ancho="820px" @cerrar="sel = null; ajuste = null">
      <p class="sub">UNSPSC {{ sel.articulo.codigo_unspsc }} · {{ sel.articulo.unidad }}</p>
      <div v-if="sel.atipico_sugerido" class="alert warn">La dispersión supera el umbral. Se sugiere revisar el precio resaltado en rojo como posible atípico.</div>
      <h3>Cotizaciones</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Ref.</th><th>Proveedor</th><th>Fecha</th><th class="right">Precio</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="c in sel.cotizaciones" :key="c.item_id" :class="{ dis: c.excluido }">
            <td>{{ c.etiqueta }}</td><td>{{ c.proveedor }}</td><td>{{ fecha(c.fecha) }}</td>
            <td class="right mono" :style="c.item_id === sel.atipico_sugerido ? 'color:var(--rojo);font-weight:700' : ''">{{ money(c.precio) }}</td>
            <td class="small">{{ c.excluido ? `Excluida: ${c.motivo}` : 'Válida' }}</td>
            <td class="right nowrap">
              <a :href="api.pdfUrl(c.cotizacion_id)" target="_blank" rel="noopener" class="small">PDF</a>
              <template v-if="editable">
                <button v-if="c.excluido" class="btn ghost sm" @click="excluir(c, false)">Reincorporar</button>
                <template v-else>
                  <button class="btn ghost sm" @click="excluir(c, true, 'su valor notoriamente alto')">Excluir (alto)</button>
                  <button class="btn ghost sm" @click="excluir(c, true, 'su valor notoriamente bajo')">Excluir (bajo)</button>
                </template>
              </template>
            </td>
          </tr>
          <tr v-if="!sel.cotizaciones.length"><td colspan="6" class="muted">Sin cotizaciones en esta vigencia</td></tr>
        </tbody>
      </table></div>
      <h3 style="margin-top:14px">Precios históricos (indexados con IPC + puntos)</h3>
      <table><tbody>
        <tr v-for="h in sel.historicos" :key="h.anio"><td>{{ h.anio }}</td><td class="right mono">{{ money(h.precio) }}</td><td class="small muted">× {{ h.factor.toFixed(4) }}</td><td class="right mono">{{ money(h.indexado) }}</td><td class="small muted">{{ h.fuente }}</td></tr>
        <tr v-if="!sel.historicos.length"><td class="muted">Sin históricos</td></tr>
      </tbody></table>
      <div class="card" style="margin-top:14px;background:var(--fila)">
        <div><b>Método:</b> {{ sel.metodo || '—' }}{{ sel.metodo_manual ? ' (manual)' : ' (automático)' }} · <b>Precio estimado:</b> {{ money(sel.precio_estimado) }} · <b>Dispersión final:</b> {{ pct(sel.dispersion_final) }}</div>
        <p class="small" style="margin:8px 0 0"><b>Análisis:</b> {{ sel.justificacion || '—' }}</p>
      </div>
      <div v-if="ajuste" class="form-grid" style="margin-top:14px">
        <label class="f"><span>Método</span>
          <select v-model="ajuste.metodo"><option value="">Automático (reglas)</option><option value="COTIZACIONES">Cotizaciones</option><option value="HISTORICOS">Históricos</option><option value="EXPERTO">Precio de experto</option></select>
        </label>
        <label class="f" :class="{ req: ajuste.metodo === 'EXPERTO' }"><span>Precio de experto</span><input v-model.number="ajuste.precio_experto" type="number" min="0" /></label>
        <label class="f full" :class="{ req: ajuste.metodo }"><span>Justificación (aparece en el formato)</span><textarea v-model="ajuste.justificacion" rows="3" /></label>
      </div>
      <template #pie>
        <template v-if="editable">
          <button v-if="!ajuste" class="btn ghost" @click="abrirAjuste(sel)">Ajustar método / precio experto</button>
          <template v-else><button class="btn ghost" @click="ajuste = null">Cancelar</button><button class="btn" @click="guardarAjuste">Guardar ajuste</button></template>
        </template>
      </template>
    </Modal>
  </div>
</template>
