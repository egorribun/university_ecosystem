import { IconButton, Badge } from "@mui/material"
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"

export default function MessengerButton() {
  const navigate = useNavigate()
  const { t } = useTranslation(["navigation"])

  // Mock unread count for now
  const unreadCount = 0

  return (
    <IconButton
      color="inherit"
      onClick={() => navigate("/messenger")}
      aria-label={t("navigation:aria.messenger")}
    >
      <Badge badgeContent={unreadCount} color="error">
        <ChatBubbleOutlineIcon />
      </Badge>
    </IconButton>
  )
}
