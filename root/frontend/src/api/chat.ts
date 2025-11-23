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
        if (files && files.length > 0) {
            files.forEach(file => {
                console.log('Appending file:', file.name, file.type, file.size)
                formData.append('files', file)
            })
        }
        // Log FormData entries for debugging
        // @ts-expect-error - FormData.entries() iterator type
        for (const pair of formData.entries()) {
            console.log('FormData entry:', pair[0], pair[1]);
        }
        const response = await client.post<Message>(`/chats/${chatId}/messages`, formData)
        return response.data
    },

    markRead: async (chatId: string) => {
        const response = await client.post(`/chats/${chatId}/read`)
        return response.data
    },
}
