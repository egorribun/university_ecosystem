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
      size="small"
      onClick={() => navigate("/messenger")}
      aria-label={t("navigation:aria.messenger")}
      sx={{
        width: 'clamp(32px, 8vw, 36px)',
        height: 'clamp(32px, 8vw, 36px)',
        padding: 0,
        color: 'rgba(255, 255, 255, 0.92)'
      }}
    >
      <Badge badgeContent={unreadCount} color="error">
        <ChatBubbleOutlineIcon sx={{ color: 'inherit' }} />
      </Badge>
    </IconButton>
  )
}
