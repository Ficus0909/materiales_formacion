<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import { useAuth } from '../../store'
import { number, toast, toastError } from '../../util'

// Formulario del GIL-F-014: nueva solicitud o corrección de una enviada/devuelta (prop id)
const props = defineProps({ id: [String, Number] })
const auth = useAuth()
const router = useRouter()
const lotes = ref([])
const coordinaciones = ref([])
const catalogo = ref([])
const original = ref(null) // al corregir: cantidades ya solicitadas (no cuentan contra el saldo)
const q = ref('')
const enviando = ref(false)
const f = ref({ lote_id: '', coordinacion_id: auth.usuario.coordinacion_id, tipo_cuentadante: 'UNIPERSONAL', nombre_cuentadante: '',
  documento_cuentadante: '', integrantes: [{ nombre: '', documento: '' }, { nombre: '', documento: '' }], destino: 'FORMACION', ficha: '' })
const cantidades = ref({}) // solicitud_item_id -> { cantidad, observacion }

onMounted(async () => {
  try {
    ;[lotes.value, coordinaciones.value] = await Promise.all([api.get('/entregas/lotes'), api.get('/coordinaciones')])
    if (props.id) {
      const e = await api.get(`/entregas/${props.id}`)
      original.value = e
      Object.assign(f.value, { lote_id: e.lote_id, coordinacion_id: e.coordinacion_id, tipo_cuentadante: e.tipo_cuentadante,
        nombre_cuentadante: e.tipo_cuentadante === 'MULTIPLE' ? e.nombre_cuentadante : '', documento_cuentadante: e.tipo_cuentadante === 'MULTIPLE' ? e.documento_cuentadante : '',
        integrantes: e.integrantes.length ? e.integrantes : f.value.integrantes, destino: e.destino, ficha: e.ficha })
      cantidades.value = Object.fromEntries(e.items.map((i) => [i.solicitud_item_id, { cantidad: i.cantidad_solicitada, observacion: i.observacion }]))
    } else if (lotes.value.length === 1) f.value.lote_id = lotes.value[0].id
  } catch (e) { toastError(e) }
})
watch(() => f.value.lote_id, async (lote, anterior) => {
  if (!lote) return
  if (anterior && !original.value) cantidades.value = {}
  try {
    const cat = await api.get(`/entregas/catalogo?lote_id=${lote}`)
    // Al corregir, los bienes ya solicitados se muestran aunque su saldo libre sea 0
    if (original.value && original.value.lote_id === lote) {
      for (const i of original.value.items) {
        const c = cat.find((x) => x.solicitud_item_id === i.solicitud_item_id)
        if (c) c.disponible = Math.max(c.disponible, i.disponible)
        else cat.push({ solicitud_item_id: i.solicitud_item_id, nombre: i.nombre, unidad: i.unidad, descripcion: i.descripcion, disponible: i.disponible })
      }
    }
    catalogo.value = cat.sort((a, b) => a.nombre.localeCompare(b.nombre))
    for (const c of catalogo.value) cantidades.value[c.solicitud_item_id] ||= { cantidad: '', observacion: '' }
  } catch (e) { toastError(e) }
})

const visibles = computed(() => catalogo.value.filter((c) => !q.value || c.nombre.toLowerCase().includes(q.value.toLowerCase())))
const seleccion = computed(() => Object.entries(cantidades.value).filter(([, v]) => Number(v.cantidad) > 0))
const excede = (c) => Number(cantidades.value[c.solicitud_item_id]?.cantidad || 0) > c.disponible

async function enviar() {
  if (!seleccion.value.length) return toast('Indique la cantidad de al menos un bien', 'error')
  if (catalogo.value.some(excede)) return toast('Hay cantidades mayores al saldo disponible', 'error')
  enviando.value = true
  const body = { ...f.value, integrantes: f.value.tipo_cuentadante === 'MULTIPLE' ? f.value.integrantes : [],
    items: seleccion.value.map(([id, v]) => ({ solicitud_item_id: Number(id), cantidad: Number(v.cantidad), observacion: v.observacion || '' })) }
  try {
    const r = props.id ? await api.put(`/entregas/${props.id}`, body) : await api.post('/entregas', body)
    toast(`Solicitud N° ${r.id} enviada al coordinador de la ${r.coordinacion}`)
    router.push(`/entregas/${r.id}`)
  } catch (e) { toastError(e) } finally { enviando.value = false }
}
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>{{ props.id ? `Corregir solicitud N° ${props.id}` : 'Solicitar materiales' }}</h1>
        <div class="sub">Formato GIL-F-014 · Solicitud de bienes para uso de cuentadantes</div></div>
    </div>
    <div v-if="original?.estado === 'DEVUELTA'" class="alert warn"><b>Observaciones del coordinador:</b> {{ original.observaciones_coordinador }}</div>
    <div v-if="!auth.usuario.documento" class="alert error">Registre su número de identificación en <router-link to="/perfil">Mi perfil</router-link> antes de solicitar.</div>
    <div v-if="!lotes.length" class="alert info">Aún no hay material disponible: los lotes aparecen aquí cuando sus materiales llegan al centro («En el Punto»).</div>
    <form @submit.prevent="enviar">
      <div class="card">
        <h2>Datos de la solicitud</h2>
        <div class="form-grid">
          <label class="f req"><span>Lote</span><select v-model="f.lote_id" required :disabled="!!props.id"><option value="" disabled>Seleccione…</option><option v-for="l in lotes" :key="l.id" :value="l.id">{{ l.numero }}. {{ l.nombre }} ({{ l.articulos_disponibles }} bienes)</option></select></label>
          <label class="f req"><span>Coordinación (área)</span><select v-model="f.coordinacion_id" required><option v-for="c in coordinaciones.filter((c) => c.activo)" :key="c.id" :value="c.id">{{ c.nombre }}</option></select></label>
          <label class="f req"><span>Destino de los bienes</span><select v-model="f.destino"><option value="FORMACION">Formación</option><option value="ADMINISTRATIVA">Área administrativa</option></select></label>
          <label class="f" :class="{ req: f.destino === 'FORMACION' }"><span>Código de grupo o ficha de caracterización</span><input v-model="f.ficha" :required="f.destino === 'FORMACION'" placeholder="Ej. 2671234" /></label>
          <label class="f req"><span>Tipo de cuentadante</span><select v-model="f.tipo_cuentadante"><option value="UNIPERSONAL">Unipersonal (usted)</option><option value="MULTIPLE">Múltiple (grupo de personas)</option></select></label>
          <template v-if="f.tipo_cuentadante === 'UNIPERSONAL'">
            <div class="f"><span>Cuentadante</span><div class="muted" style="padding:8px 0">{{ auth.usuario.nombre }} · C.C. {{ auth.usuario.documento || '—' }}</div></div>
          </template>
          <template v-else>
            <label class="f req"><span>Nombre del cuentadante múltiple</span><input v-model="f.nombre_cuentadante" required placeholder="Ej. Grupo avícola ficha 2671234" /></label>
            <label class="f"><span>N° de identificación (si lo conoce)</span><input v-model="f.documento_cuentadante" /></label>
          </template>
        </div>
        <div v-if="f.tipo_cuentadante === 'MULTIPLE'" style="margin-top:10px">
          <div class="small muted" style="margin-bottom:6px">Personas que conforman el cuentadante múltiple (mínimo dos):</div>
          <div v-for="(p, i) in f.integrantes" :key="i" class="row" style="margin-bottom:6px">
            <input v-model="p.nombre" placeholder="Nombre" class="grow" required /><input v-model="p.documento" placeholder="N° de identificación" required />
            <button type="button" class="btn ghost sm" :disabled="f.integrantes.length <= 2" @click="f.integrantes.splice(i, 1)">✕</button>
          </div>
          <button type="button" class="btn ghost sm" @click="f.integrantes.push({ nombre: '', documento: '' })">+ Agregar persona</button>
        </div>
      </div>
      <div v-if="f.lote_id" class="card">
        <div class="row" style="justify-content:space-between;margin-bottom:10px">
          <h2 style="margin:0">Bienes solicitados <span class="small muted">({{ seleccion.length }} seleccionados)</span></h2>
          <input v-model="q" placeholder="Buscar bien…" />
        </div>
        <div class="table-wrap tall">
          <table>
            <thead><tr><th>Descripción del bien</th><th>Unidad</th><th class="right">Disponible</th><th class="right" style="width:120px">Cantidad solicitada</th><th>Observaciones</th></tr></thead>
            <tbody>
              <tr v-for="c in visibles" :key="c.solicitud_item_id" :style="{ background: Number(cantidades[c.solicitud_item_id]?.cantidad) > 0 ? '#F1F8EC' : '' }">
                <td>{{ c.nombre }}<div v-if="c.descripcion" class="small muted">{{ c.descripcion.slice(0, 140) }}</div></td>
                <td>{{ c.unidad }}</td><td class="right">{{ number(c.disponible) }}</td>
                <td class="right"><input v-model="cantidades[c.solicitud_item_id].cantidad" type="number" min="0" :max="c.disponible" step="any" style="width:100px;text-align:right" :style="{ borderColor: excede(c) ? 'var(--rojo)' : '' }" /></td>
                <td><input v-model="cantidades[c.solicitud_item_id].observacion" maxlength="300" style="width:100%" /></td>
              </tr>
              <tr v-if="!visibles.length"><td colspan="5" class="empty">Sin bienes disponibles</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="row" style="justify-content:flex-end">
        <router-link :to="props.id ? `/entregas/${props.id}` : '/instructor'" class="btn ghost">Cancelar</router-link>
        <button class="btn" :disabled="enviando || !f.lote_id || !auth.usuario.documento">{{ enviando ? 'Enviando…' : 'Enviar al coordinador' }}</button>
      </div>
    </form>
  </div>
</template>
