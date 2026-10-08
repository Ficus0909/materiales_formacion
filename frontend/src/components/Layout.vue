<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useAuth } from '../store'
import { fecha, fechaHora } from '../util'

const auth = useAuth()
const router = useRouter()
const abierto = ref(false)
const panel = ref(false)
const notifs = ref({ no_leidas: 0, items: [] })
const online = ref(navigator.onLine)

const menu = computed(() => auth.esManager
  ? [
      ['/manager', 'Dashboard', '▦'], ['/manager/centros', 'Centros de formación', '⌂'], ['/admin/usuarios', 'Usuarios', '☺'],
      ['/admin/solicitudes', 'Solicitudes', '✉'], ['/reportes', 'Reportes', '▮'], ['/admin/vigencias', 'Vigencias', '◷'],
      ['/admin/proveedores', 'Proveedores', '$'], ['/admin/configuracion', 'Configuración', '⚙'],
    ]
  : auth.esAdmin
  ? [
      ['/admin', 'Dashboard', '▦'], ['/admin/solicitudes', 'Solicitudes', '✉'], ['/admin/analisis', 'Análisis de precios', '％'],
      ['/admin/listado-maestro', 'Listado maestro', '☰'], ['/admin/propuestas', 'Artículos propuestos', '✚'],
      ['/admin/proveedores', 'Proveedores', '⌂'], ['/admin/vigencias', 'Vigencias', '◷'], ['/admin/lotes', 'Lotes', '▤'],
      ['/admin/usuarios', 'Usuarios', '☺'], ['/reportes', 'Reportes', '▮'], ['/admin/configuracion', 'Configuración', '⚙'],
    ]
  : [
      ['/lider', 'Mi dashboard', '▦'], ['/lider/mi-lote', 'Mi lote', '☰'], ['/lider/cotizaciones', 'Cotizaciones', '$'],
      ['/lider/mi-solicitud', 'Mi solicitud', '✉'], ['/lider/seguimiento', 'Seguimiento', '◉'], ['/reportes', 'Reportes', '▮'],
    ])

async function cargarNotifs() {
  try { notifs.value = await api.get('/notificaciones') } catch { /* sin conexión */ }
}
async function abrirNotif(n) {
  panel.value = false
  if (!n.leida) { await api.post('/notificaciones/leer', [n.id]); cargarNotifs() }
  if (n.enlace) router.push(n.enlace.replace('/admin/solicitudes/', '/solicitudes/'))
}
async function leerTodas() { await api.post('/notificaciones/leer', []); cargarNotifs() }
async function salir() { await auth.logout(); router.push('/login') }

let timer
const onOff = () => { online.value = navigator.onLine }
onMounted(() => {
  cargarNotifs()
  timer = setInterval(cargarNotifs, 30000)
  window.addEventListener('online', onOff)
  window.addEventListener('offline', onOff)
})
onUnmounted(() => {
  clearInterval(timer)
  window.removeEventListener('online', onOff)
  window.removeEventListener('offline', onOff)
})
const rolTexto = computed(() => auth.esManager ? 'Manager · todos los centros'
  : auth.esAdmin ? 'Administrador / Analista' : `Líder · ${auth.usuario?.lote?.nombre}`)
const iniciales = computed(() => (auth.usuario?.nombre || '?').split(' ').map((p) => p[0]).slice(0, 2).join(''))
</script>

<template>
  <div class="shell">
    <header class="top">
      <button class="ham" aria-label="Menú" @click="abierto = !abierto">☰</button>
      <router-link to="/" class="brand"><img src="/logo-sena-blanco.png" alt="SENA" class="logo" /><span>Materiales de Formación</span></router-link>
      <span v-if="auth.vigencia" class="vig">Vigencia <b>{{ auth.vigencia.codigo }}</b> · cierra {{ fecha(auth.vigencia.fecha_cierre) }}</span>
      <span v-else class="vig">Sin vigencia abierta</span>
      <span class="grow" />
      <div class="bell-wrap">
        <button class="bell" aria-label="Notificaciones" @click="panel = !panel">🔔<span v-if="notifs.no_leidas" class="cnt">{{ notifs.no_leidas }}</span></button>
        <div v-if="panel" class="np">
          <div class="row" style="justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--borde)">
            <b>Notificaciones</b><button class="link small" @click="leerTodas">Marcar todas leídas</button>
          </div>
          <div v-if="!notifs.items.length" class="empty">Sin notificaciones</div>
          <button v-for="n in notifs.items" :key="n.id" class="ni" :class="{ nueva: !n.leida }" @click="abrirNotif(n)">
            <b>{{ n.titulo }}</b><span v-if="n.mensaje" class="small">{{ n.mensaje }}</span>
            <span class="small muted">{{ fechaHora(n.fecha) }}</span>
          </button>
        </div>
      </div>
      <span class="av" :title="auth.usuario?.email">{{ iniciales }}</span>
    </header>
    <div v-if="!online" class="offline">Sin conexión: está viendo datos guardados. Los cambios no se podrán guardar hasta reconectarse.</div>
    <aside class="side" :class="{ open: abierto }" @click="abierto = false">
      <nav>
        <router-link v-for="[to, txt, ic] in menu" :key="to" :to="to" class="it" :exact-active-class="'on'"
                     :active-class="['/admin', '/lider', '/manager'].includes(to) ? '' : 'on'">
          <span class="ic">{{ ic }}</span>{{ txt }}
        </router-link>
      </nav>
      <div class="me">
        <div><b>{{ auth.usuario?.nombre }}</b></div>
        <div class="small" style="opacity:.75">{{ rolTexto }}</div>
        <div v-if="auth.usuario?.centro" class="small" style="opacity:.6">{{ auth.usuario.centro.nombre }}</div>
        <div class="row" style="margin-top:8px;gap:10px">
          <router-link to="/cambiar-password" class="small" style="color:#cfe">Contraseña</router-link>
          <button class="link small" style="color:#ffb4b4" @click="salir">Cerrar sesión</button>
        </div>
      </div>
    </aside>
    <div v-if="abierto" class="scrim" @click="abierto = false" />
    <main class="main"><router-view /></main>
  </div>
</template>

<style scoped>
.shell { min-height: 100vh; }
.top { position: sticky; top: 0; z-index: 30; height: 56px; display: flex; align-items: center; gap: 12px; padding: 0 16px; color: #fff; background: linear-gradient(90deg, var(--verde), var(--azul)); border-bottom: 4px solid var(--verde); }
.brand { display: flex; align-items: center; gap: 10px; color: #fff; text-decoration: none; font-weight: 700; font-size: 16px; }
.logo { height: 38px; width: auto; display: block; }
.vig { font-size: 12px; opacity: .9; background: rgba(255,255,255,.14); padding: 4px 10px; border-radius: 99px; }
.ham { display: none; background: none; border: 0; color: #fff; font-size: 22px; cursor: pointer; }
.bell-wrap { position: relative; }
.bell { background: none; border: 0; font-size: 18px; cursor: pointer; position: relative; }
.cnt { position: absolute; top: -6px; right: -8px; background: var(--rojo); color: #fff; font-size: 10px; border-radius: 99px; padding: 1px 5px; font-weight: 700; }
.np { position: absolute; right: 0; top: 36px; width: min(360px, calc(100vw - 24px)); max-height: 70vh; overflow: auto; background: #fff; color: var(--texto); border-radius: 8px; box-shadow: 0 12px 30px rgba(0,0,0,.2); }
.ni { display: grid; gap: 2px; width: 100%; text-align: left; background: #fff; border: 0; border-bottom: 1px solid var(--borde); padding: 10px 12px; font: inherit; font-size: 13px; cursor: pointer; }
.ni.nueva { background: #F1F8EC; border-left: 3px solid var(--verde); }
.av { width: 32px; height: 32px; border-radius: 50%; background: var(--naranja); display: grid; place-items: center; font-weight: 700; font-size: 13px; }
.side { position: fixed; top: 60px; bottom: 0; left: 0; width: 230px; background: var(--azul); color: #fff; display: flex; flex-direction: column; justify-content: space-between; padding: 12px 10px; z-index: 20; overflow-y: auto; }
.it { display: flex; align-items: center; gap: 10px; color: #E2E8F0; text-decoration: none; padding: 9px 12px; border-radius: 8px; font-size: 13px; margin-bottom: 2px; }
.it:hover { background: rgba(255,255,255,.08); }
.it.on { background: var(--verde); color: #fff; font-weight: 600; }
.ic { width: 18px; text-align: center; opacity: .9; }
.me { border-top: 1px solid rgba(255,255,255,.15); padding: 12px 8px 4px; font-size: 13px; }
.main { margin-left: 230px; padding: 20px 24px 40px; max-width: 1500px; }
.offline { background: var(--amarillo); color: var(--texto); padding: 6px 16px; font-size: 13px; text-align: center; position: sticky; top: 60px; z-index: 25; }
.scrim { display: none; }
@media (max-width: 900px) {
  .ham { display: block; }
  .vig { display: none; }
  .side { transform: translateX(-100%); transition: transform .2s; width: 250px; }
  .side.open { transform: none; }
  .scrim { display: block; position: fixed; inset: 60px 0 0; background: rgba(0,0,0,.35); z-index: 15; }
  .main { margin-left: 0; padding: 16px; }
}
</style>
