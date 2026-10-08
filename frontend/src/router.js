import { createRouter, createWebHistory } from 'vue-router'
import { setUnauthorizedHandler } from './api'
import { useAuth } from './store'

const A = (n) => () => import(`./views/admin/${n}.vue`)
const L = (n) => () => import(`./views/lider/${n}.vue`)
const M = (n) => () => import(`./views/manager/${n}.vue`)
const AM = ['ADMIN', 'MANAGER']

const routes = [
  { path: '/login', component: () => import('./views/Login.vue'), meta: { publica: true } },
  {
    path: '/',
    component: () => import('./components/Layout.vue'),
    children: [
      { path: '', redirect: () => useAuth().inicio },
      { path: 'cambiar-password', component: () => import('./views/CambiarPassword.vue') },
      { path: 'reportes', component: () => import('./views/Reportes.vue') },
      { path: 'solicitudes/:id', component: () => import('./views/DetalleSolicitud.vue'), props: true },
      { path: 'admin', component: A('Dashboard'), meta: { rol: 'ADMIN' } },
      { path: 'manager', component: M('Dashboard'), meta: { rol: 'MANAGER' } },
      { path: 'manager/centros', component: M('Centros'), meta: { rol: 'MANAGER' } },
      { path: 'admin/usuarios', component: A('Usuarios'), meta: { rol: AM } },
      { path: 'admin/lotes', component: A('Lotes'), meta: { rol: 'ADMIN' } },
      { path: 'admin/vigencias', component: A('Vigencias'), meta: { rol: AM } },
      { path: 'admin/listado-maestro', component: A('ListadoMaestro'), meta: { rol: 'ADMIN' } },
      { path: 'admin/proveedores', component: A('Proveedores'), meta: { rol: AM } },
      { path: 'admin/analisis', component: A('Analisis'), meta: { rol: 'ADMIN' } },
      { path: 'admin/solicitudes', component: A('Bandeja'), meta: { rol: AM } },
      { path: 'admin/solicitudes/:id', redirect: (to) => `/solicitudes/${to.params.id}` },
      { path: 'admin/propuestas', component: A('Propuestas'), meta: { rol: 'ADMIN' } },
      { path: 'admin/configuracion', component: A('Configuracion'), meta: { rol: AM } },
      { path: 'lider', component: L('Dashboard'), meta: { rol: 'LIDER' } },
      { path: 'lider/mi-lote', component: L('MiLote'), meta: { rol: 'LIDER' } },
      { path: 'lider/cotizaciones', component: L('Cotizaciones'), meta: { rol: 'LIDER' } },
      { path: 'lider/mi-solicitud', component: L('MiSolicitud'), meta: { rol: 'LIDER' } },
      { path: 'lider/seguimiento', component: L('Seguimiento'), meta: { rol: 'LIDER' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) })

router.beforeEach(async (to) => {
  const auth = useAuth()
  await auth.verificar()
  if (to.meta.publica) return auth.usuario ? auth.inicio : true
  if (!auth.usuario) return { path: '/login', query: { r: to.fullPath } }
  if (auth.usuario.debe_cambiar_password && to.path !== '/cambiar-password') return '/cambiar-password'
  if (to.meta.rol && ![].concat(to.meta.rol).includes(auth.usuario.rol)) return auth.inicio
  return true
})

setUnauthorizedHandler(() => {
  const auth = useAuth()
  if (auth.usuario) { auth.logout(); router.push('/login') }
})

export default router
