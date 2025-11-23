import client from "./client"
import type { User } from "../types/User"

export interface Attachment {
    id: string
    url: string
    type: 'image' | 'video' | 'file'
    name: string
    size: number
}

export interface Message {
    id: string
    chat_id: string
    sender_id: string
    content: string
    created_at: string
    read_status: boolean
    sender?: User
    attachments?: Attachment[]
}

export interface Chat {
    id: string
    participants: User[]
    last_message?: Message
    unread_count: number
    created_at: string
    updated_at: string
}

export const chatApi = {
    getChats: async () => {
        const response = await client.get<Chat[]>("/chats")
        return response.data
    },

    createChat: async (participantId: string) => {
        const response = await client.post<Chat>("/chats", { participant_id: Number(participantId) })
        return response.data
    },

    getMessages: async (chatId: string) => {
        const response = await client.get<Message[]>(`/chats/${chatId}/messages`)
        return response.data
    },

    sendMessage: async (chatId: string, content: string, files?: File[]) => {
        console.log('chatApi.sendMessage:', { chatId, content, filesCount: files?.length })
        const formData = new FormData()
        formData.append('content', content)
        return response.data
    },
}
