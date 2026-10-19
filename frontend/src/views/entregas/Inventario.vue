<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, qs } from '../../api'
import { useAuth } from '../../store'
import { money, number, toastError } from '../../util'

const auth = useAuth()
const lotes = ref([])
const lote = ref(auth.usuario.lote_id || '')
const d = ref(null)
const q = ref('')
const periodo = ref({ desde: '', hasta: '' })

async function cargar() {
  if (!lote.value) return
  try { d.value = await api.get(`/entregas/inventario${qs({ lote_id: auth.esLider ? '' : lote.value })}`) } catch (e) { toastError(e) }
}
onMounted(async () => {
  if (!auth.esLider) {
    lotes.value = await api.get('/lotes')
    lote.value ||= lotes.value[0]?.id || ''
  }
  cargar()
})
watch(lote, cargar)
const filas = computed(() => (d.value?.items || []).filter((f) => !q.value || f.nombre.toLowerCase().includes(q.value.toLowerCase())))
const informe = (formato) => api.descargar(`/entregas/informe${qs({ formato, lote_id: auth.esLider ? '' : lote.value, ...periodo.value })}`)
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>Inventario del lote</h1><div class="sub" v-if="d">Lote {{ d.lote.numero }}. {{ d.lote.nombre }} · material recibido, entregado a instructores y saldo</div></div>
      <select v-if="!auth.esLider" v-model="lote"><option v-for="l in lotes" :key="l.id" :value="l.id">{{ l.numero }}. {{ l.nombre }}{{ auth.esManager ? ` (${l.centro})` : '' }}</option></select>
    </div>
    <template v-if="d">
      <div class="kpis">
        <div class="card kpi"><div class="l">Valor recibido</div><div class="v" style="font-size:20px">{{ money(d.totales.valor_recibido) }}</div></div>
        <div class="card kpi" style="border-color:var(--cyan)"><div class="l">Entregado a instructores</div><div class="v" style="font-size:20px">{{ money(d.totales.valor_entregado) }}</div></div>
        <div class="card kpi" style="border-color:var(--azul)"><div class="l">Saldo</div><div class="v" style="font-size:20px">{{ money(d.totales.valor_disponible) }}</div></div>
      </div>
      <div class="card">
        <div class="row" style="justify-content:space-between;align-items:flex-end;margin-bottom:10px">
          <input v-model="q" placeholder="Buscar artículo…" />
          <div class="row" style="align-items:flex-end">
            <label class="f"><span>Entregas desde</span><input v-model="periodo.desde" type="date" /></label>
            <label class="f"><span>hasta</span><input v-model="periodo.hasta" type="date" /></label>
            <button class="btn" @click="informe('pdf')">Informe PDF</button>
            <button class="btn ghost" @click="informe('csv')">Exportar CSV</button>
          </div>
        </div>
        <div class="table-wrap tall">
          <table>
            <thead><tr><th>Artículo</th><th>Unidad</th><th class="right">Recibido</th><th class="right">Entregado</th><th class="right">Reservado</th>
              <th class="right">Saldo</th><th class="right">Precio</th><th class="right">Valor entregado</th><th class="right">Valor saldo</th></tr></thead>
            <tbody>
              <tr v-for="f in filas" :key="f.solicitud_item_id">
                <td>{{ f.nombre }}<div class="small muted">Vigencia {{ f.vigencia }}</div></td><td>{{ f.unidad }}</td>
                <td class="right">{{ number(f.recibido) }}</td><td class="right">{{ number(f.entregado) }}</td>
                <td class="right" :title="'Aprobado por el coordinador, pendiente de entrega'">{{ number(f.reservado) }}</td>
                <td class="right"><b :style="{ color: f.disponible <= 0 ? 'var(--rojo)' : '' }">{{ number(f.disponible) }}</b></td>
                <td class="right mono">{{ money(f.precio) }}</td><td class="right mono">{{ money(f.valor_entregado) }}</td><td class="right mono">{{ money(f.valor_disponible) }}</td>
              </tr>
              <tr v-if="!filas.length"><td colspan="9" class="empty">El lote aún no tiene material recibido: el inventario se forma cuando la solicitud del lote llega al final del ciclo de compra («En el Punto»).</td></tr>
            </tbody>
          </table>
        </div>
        <p class="small muted">«Reservado» es lo que un coordinador ya aprobó y está pendiente de entrega. El saldo descuenta lo entregado y lo reservado.</p>
      </div>
    </template>
  </div>
</template>
