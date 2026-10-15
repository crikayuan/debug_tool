import { createRouter, createWebHistory } from 'vue-router'
import DebugView from '../views/DebugView.vue'

const routes = [
    {
        path: '/',
        component: DebugView
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

export default router
