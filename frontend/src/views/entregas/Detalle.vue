<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import Badge from '../../components/Badge.vue'
import { useAuth } from '../../store'
import { ESTADOS, fecha, fechaHora, money, number, toast, toastError } from '../../util'

const props = defineProps({ id: [String, Number] })
const auth = useAuth()
const router = useRouter()
const e = ref(null)
const obs = ref('')
const procesando = ref(false)
const entrega = ref({}) // item id -> cantidad entregada
const fechaEntrega = ref(new Date().toISOString().slice(0, 10))
const acta = ref(null)
const fotos = ref([])
const obsLegal = ref('')
const DESTINO = { FORMACION: 'Formación', ADMINISTRATIVA: 'Área administrativa' }

async function cargar() {
  try {
    e.value = await api.get(`/entregas/${props.id}`)
    entrega.value = Object.fromEntries(e.value.items.map((i) => [i.id, i.cantidad_entregada ?? i.cantidad_solicitada]))
  } catch (err) { toastError(err) }
}
onMounted(cargar)
watch(() => props.id, cargar)

const esDueno = computed(() => auth.esInstructor && e.value?.instructor_id === auth.usuario.id)
const volver = computed(() => (auth.esInstructor ? '/instructor' : '/entregas'))
const valorEntrega = computed(() => (e.value?.items || []).reduce((t, i) => t + Number(entrega.value[i.id] || 0) * i.precio, 0))
const pasos = computed(() => {
  if (!e.value) return []
  const orden = ['ENVIADA', 'APROBADA', 'ENTREGADA', 'LEGALIZADA']
  const fechas = {}
  e.value.historial.forEach((h) => { fechas[h.estado_nuevo] = h.fecha })
  const actual = e.value.estado === 'DEVUELTA' ? 0 : orden.indexOf(e.value.estado)
  const fin = e.value.estado === 'LEGALIZADA' // proceso completo: todos los pasos con ✓
  return orden.map((p, i) => ({ clave: p, label: ESTADOS[p].label, fecha: fechas[p], estado: i < actual || fin ? 'done' : i === actual ? 'done cur' : '' }))
})

async function decidir(accion) {
  if (accion === 'DEVOLVER' && !obs.value.trim()) return toast('Indique al instructor qué debe corregir', 'error')
  if (accion === 'APROBAR' && !auth.usuario.tiene_firma) return toast('Cargue primero su firma en «Mi firma y perfil»', 'error')
  if (!confirm(accion === 'APROBAR' ? '¿Aprobar y firmar el formato GIL-F-014? Se reservará el material del lote.' : '¿Devolver la solicitud al instructor?')) return
  procesando.value = true
  try { e.value = await api.post(`/entregas/${props.id}/decidir`, { accion, observaciones: obs.value }); obs.value = ''; toast(accion === 'APROBAR' ? 'Solicitud aprobada y firmada' : 'Solicitud devuelta al instructor') } catch (err) { toastError(err) } finally { procesando.value = false }
}
async function entregar() {
  if (!confirm(`¿Registrar la entrega por ${money(valorEntrega.value)}? Se descontará del inventario del lote y empezará el plazo de legalización del instructor.`)) return
  procesando.value = true
  try {
    e.value = await api.post(`/entregas/${props.id}/entregar`, { fecha_entrega: fechaEntrega.value,
      items: e.value.items.map((i) => ({ id: i.id, cantidad_entregada: Number(entrega.value[i.id] || 0) })) })
    toast(`Entrega registrada. El instructor debe legalizar antes del ${fecha(e.value.fecha_limite_legalizacion)}`)
  } catch (err) { toastError(err) } finally { procesando.value = false }
}
async function legalizar() {
  if (!acta.value) return toast('Adjunte el acta de entrega firmada', 'error')
  if (fotos.value.length < 3 || fotos.value.length > 5) return toast('Adjunte entre 3 y 5 fotos', 'error')
  const fd = new FormData()
  fd.append('acta', acta.value)
  fotos.value.forEach((f) => fd.append('fotos', f))
  fd.append('observaciones', obsLegal.value)
  procesando.value = true
  try { e.value = await api.post(`/entregas/${props.id}/legalizar`, fd); toast('Entrega legalizada') } catch (err) { toastError(err) } finally { procesando.value = false }
}
async function anular() {
  if (!confirm('¿Anular esta solicitud? Se eliminará.')) return
  try { await api.del(`/entregas/${props.id}`); toast('Solicitud anulada'); router.push('/instructor') } catch (err) { toastError(err) }
}
const elegirFotos = (ev) => { fotos.value = [...ev.target.files] }
</script>

<template>
  <div v-if="e">
    <div class="page-head">
      <div>
        <div class="sub"><router-link :to="volver">‹ Volver</router-link></div>
        <h1>Solicitud de bienes N° {{ e.id }} <Badge :estado="e.extemporanea ? 'EXTEMPORANEA' : e.estado" /></h1>
        <div class="sub">{{ e.instructor }} · {{ e.coordinacion }} · Lote {{ e.lote_numero }}. {{ e.lote }}<span v-if="auth.esManager"> · {{ e.centro }}</span> · Solicitada {{ fecha(e.fecha_solicitud) }}</div>
      </div>
      <div class="row">
        <div class="card" style="padding:10px 16px"><div class="small muted">{{ ['ENTREGADA', 'LEGALIZADA'].includes(e.estado) ? 'Valor entregado' : 'Valor solicitado' }}</div><div style="font-size:20px;font-weight:700" class="mono">{{ money(e.valor) }}</div></div>
        <a class="btn ghost" :href="api.archivoUrl(`/entregas/${e.id}/f014.pdf`)" target="_blank" rel="noopener">📄 Formato GIL-F-014</a>
      </div>
    </div>

    <div class="card"><div class="stepper">
      <div v-for="p in pasos" :key="p.clave" class="step" :class="p.estado">
        <div class="c">{{ p.estado === 'done' ? '✓' : '' }}</div>
        <div><b v-if="p.estado.includes('cur')">{{ p.label }}</b><span v-else>{{ p.label }}</span></div>
        <div class="small muted">{{ p.fecha ? fecha(p.fecha) : '' }}</div>
      </div>
    </div></div>

    <div v-if="e.estado === 'DEVUELTA'" class="alert warn" style="margin-top:16px"><b>Devuelta por el coordinador:</b> {{ e.observaciones_coordinador }}</div>
    <div v-if="e.estado === 'ENTREGADA'" class="alert" :class="e.extemporanea ? 'error' : 'warn'" style="margin-top:16px">
      <template v-if="e.extemporanea"><b>Legalización EXTEMPORÁNEA:</b> el plazo venció el {{ fecha(e.fecha_limite_legalizacion) }}<span v-if="e.avisos_extemporaneo"> · {{ e.avisos_extemporaneo }} aviso(s) enviado(s)</span>.</template>
      <template v-else><b>Legalización pendiente:</b> plazo hasta el {{ fecha(e.fecha_limite_legalizacion) }} ({{ e.dias_habiles_restantes }} días hábiles restantes).</template>
    </div>

    <div class="cols-2">
      <div class="card">
        <h2>Datos del formato</h2>
        <table class="kv"><tbody>
          <tr><th>Área</th><td>{{ e.coordinacion }}</td></tr>
          <tr><th>Cuentadante</th><td>{{ e.tipo_cuentadante === 'MULTIPLE' ? 'Múltiple' : 'Unipersonal' }} · {{ e.nombre_cuentadante }}<span v-if="e.documento_cuentadante"> · {{ e.documento_cuentadante }}</span></td></tr>
          <tr v-if="e.integrantes.length"><th>Integrantes</th><td><div v-for="(p, i) in e.integrantes" :key="i">{{ p.nombre }} · {{ p.documento }}</div></td></tr>
          <tr><th>Destino</th><td>{{ DESTINO[e.destino] }}</td></tr>
          <tr><th>Grupo o ficha</th><td>{{ e.ficha || '—' }}</td></tr>
          <tr v-if="e.coordinador"><th>Autorizó</th><td>{{ e.coordinador }} · {{ fecha(e.fecha_aprobacion) }}<span v-if="e.firmada"> · firmado</span></td></tr>
          <tr v-if="e.fecha_entrega"><th>Entregado</th><td>{{ fecha(e.fecha_entrega) }}</td></tr>
          <tr v-if="e.fecha_legalizacion"><th>Legalizado</th><td>{{ fecha(e.fecha_legalizacion) }}</td></tr>
        </tbody></table>
      </div>
      <div v-if="e.evidencias.length" class="card">
        <h2>Legalización</h2>
        <div v-for="v in e.evidencias.filter((x) => x.tipo === 'ACTA')" :key="v.id" style="margin-bottom:10px"><a :href="api.archivoUrl(`/entregas/${e.id}/evidencias/${v.id}`)" target="_blank" rel="noopener">📄 Acta de entrega · {{ v.nombre }}</a></div>
        <div class="fotos">
          <a v-for="v in e.evidencias.filter((x) => x.tipo === 'FOTO')" :key="v.id" :href="api.archivoUrl(`/entregas/${e.id}/evidencias/${v.id}`)" target="_blank" rel="noopener">
            <img :src="api.archivoUrl(`/entregas/${e.id}/evidencias/${v.id}`)" :alt="v.nombre" loading="lazy" />
          </a>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Bienes</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Descripción del bien</th><th>Unidad</th><th class="right">Solicitada</th>
            <th v-if="auth.esLider && e.estado === 'APROBADA'" class="right">Entregar</th><th v-else class="right">Entregada</th>
            <th class="right">Precio</th><th>Observaciones</th></tr></thead>
          <tbody>
            <tr v-for="i in e.items" :key="i.id">
              <td>{{ i.nombre }}</td><td>{{ i.unidad }}</td><td class="right">{{ number(i.cantidad_solicitada) }}</td>
              <td v-if="auth.esLider && e.estado === 'APROBADA'" class="right"><input v-model="entrega[i.id]" type="number" min="0" :max="i.cantidad_solicitada" step="any" style="width:90px;text-align:right" /></td>
              <td v-else class="right">{{ i.cantidad_entregada === null ? '—' : number(i.cantidad_entregada) }}</td>
              <td class="right mono">{{ money(i.precio) }}</td><td class="small">{{ i.observacion }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Coordinador: aprobar (firma) o devolver -->
    <div v-if="auth.esCoordinador && e.estado === 'ENVIADA'" class="card">
      <h2>Revisión del coordinador</h2>
      <div v-if="!auth.usuario.tiene_firma" class="alert warn">Para aprobar debe cargar su firma digital en <router-link to="/perfil">Mi firma y perfil</router-link>.</div>
      <p class="sub">Al aprobar, su firma se estampa en el formato GIL-F-014 y el material queda reservado para este instructor.</p>
      <label class="f"><span>Observaciones (obligatorias para devolver)</span><textarea v-model="obs" rows="3" /></label>
      <div class="row" style="justify-content:flex-end;margin-top:12px">
        <button class="btn amarillo" :disabled="procesando" @click="decidir('DEVOLVER')">Devolver</button>
        <button class="btn" :disabled="procesando || !auth.usuario.tiene_firma" @click="decidir('APROBAR')">Aprobar y firmar</button>
      </div>
    </div>

    <!-- Líder: registrar entrega -->
    <div v-if="auth.esLider && e.estado === 'APROBADA'" class="card">
      <h2>Registrar entrega</h2>
      <p class="sub">Diligencie arriba la cantidad entregada de cada bien (puede ser menor a la solicitada según existencias). Lo entregado se descuenta del inventario del lote; lo no entregado vuelve al saldo.</p>
      <div class="row" style="justify-content:space-between;align-items:flex-end">
        <label class="f"><span>Fecha de entrega</span><input v-model="fechaEntrega" type="date" :max="new Date().toISOString().slice(0, 10)" /></label>
        <div class="row"><span>Valor a entregar: <b class="mono">{{ money(valorEntrega) }}</b></span><button class="btn" :disabled="procesando" @click="entregar">Registrar entrega</button></div>
      </div>
    </div>

    <!-- Instructor: legalizar -->
    <div v-if="esDueno && e.estado === 'ENTREGADA'" class="card">
      <h2>Legalizar la entrega</h2>
      <p class="sub">Cargue el acta de entrega en formato físico (firmada y escaneada o fotografiada) y entre 3 y 5 fotos que evidencien la entrega de los materiales a los aprendices.</p>
      <div class="form-grid">
        <label class="f req"><span>Acta de entrega (PDF, JPG o PNG)</span><input type="file" accept="application/pdf,image/png,image/jpeg" @change="acta = $event.target.files[0]" /></label>
        <label class="f req"><span>Fotos de la entrega ({{ fotos.length }} seleccionadas)</span><input type="file" accept="image/png,image/jpeg" multiple @change="elegirFotos" /></label>
        <label class="f full"><span>Observaciones</span><input v-model="obsLegal" /></label>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" :disabled="procesando" @click="legalizar">{{ procesando ? 'Cargando…' : 'Legalizar' }}</button></div>
    </div>

    <div v-if="esDueno && ['ENVIADA', 'DEVUELTA'].includes(e.estado)" class="row" style="justify-content:flex-end;margin-bottom:16px">
      <button class="btn ghost" style="color:var(--rojo)" @click="anular">Anular solicitud</button>
      <router-link :to="`/instructor/solicitar/${e.id}`" class="btn">Corregir</router-link>
    </div>

    <div class="card">
      <h2>Historial</h2>
      <div class="table-wrap"><table>
        <thead><tr><th>Fecha</th><th>Estado</th><th>Responsable</th><th>Observaciones</th></tr></thead>
        <tbody><tr v-for="(h, k) in [...e.historial].reverse()" :key="k">
          <td class="nowrap">{{ fechaHora(h.fecha) }}</td>
          <td class="nowrap"><span v-if="h.estado_anterior" class="muted small">{{ ESTADOS[h.estado_anterior]?.label || h.estado_anterior }} → </span><b>{{ ESTADOS[h.estado_nuevo]?.label || h.estado_nuevo }}</b></td>
          <td>{{ h.usuario }}</td><td>{{ h.observaciones }}</td>
        </tr></tbody>
      </table></div>
    </div>
  </div>
  <div v-else class="card"><div class="skeleton" v-for="i in 6" :key="i" /></div>
</template>

<style scoped>
.kv th { text-align: left; width: 130px; color: var(--texto2); font-weight: 600; vertical-align: top; }
.kv td, .kv th { padding: 5px 6px; border-bottom: 1px solid var(--borde); }
.fotos { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; }
.fotos img { width: 100%; height: 100px; object-fit: cover; border-radius: 6px; border: 1px solid var(--borde); }
</style>
