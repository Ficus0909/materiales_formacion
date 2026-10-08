import { defineStore } from 'pinia'
import { api, token } from './api'

export const useAuth = defineStore('auth', {
  state: () => ({ usuario: null, vigencia: null, listo: false }),
  getters: {
    esAdmin: (s) => s.usuario?.rol === 'ADMIN',
    esManager: (s) => s.usuario?.rol === 'MANAGER',
    inicio: (s) => ({ MANAGER: '/manager', ADMIN: '/admin' }[s.usuario?.rol] || '/lider'),
  },
  actions: {
    async login(email, password) {
      const r = await api.post('/auth/login', { email, password })
      token.set(r.token)
      this.usuario = r.usuario
      await this.cargarVigencia()
    },
    async verificar() {
      if (this.listo) return
      if (token.get()) {
        try {
          this.usuario = await api.get('/auth/me')
          await this.cargarVigencia()
        } catch { token.set(null); this.usuario = null }
      }
      this.listo = true
    },
    async cargarVigencia() {
      try { this.vigencia = await api.get('/vigencias/activa') } catch { this.vigencia = null }
    },
    async logout() {
      token.set(null)
      this.usuario = null
      // Borra datos de la API guardados para uso sin conexión (pueden ser de otro usuario)
      try {
        for (const k of await caches.keys()) {
          const c = await caches.open(k)
          for (const req of await c.keys()) if (new URL(req.url).pathname.startsWith('/api/')) await c.delete(req)
        }
      } catch { /* sin Cache API */ }
    },
  },
})
