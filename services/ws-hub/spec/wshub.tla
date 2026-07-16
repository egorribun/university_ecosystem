--------------------------- MODULE wshub ---------------------------
EXTENDS Naturals, TLC

CONSTANTS Clients

VARIABLES 
    clientState,     \* Map of Client -> State
    locksHeld,       \* Map of Process -> Set of locks held
    locksWaiting,    \* Map of Process -> Lock waiting for (or "None")
    natsSubscribed   \* Map of Client -> Boolean (NATS subscription status)

Procs == Clients \union {"Hub"}
Locks == {"hub_mu"} \union { "client_mu_" \ o c : c \in Clients }

TypeOK == 
    /\ clientState \in [Clients -> {"Idle", "Subscribing", "Subscribed", "Active", "Disconnecting"}]
    /\ locksHeld \in [Procs -> SUBSET Locks]
    /\ locksWaiting \in [Procs -> Locks \union {"None"}]
    /\ natsSubscribed \in [Clients -> BOOLEAN]

\* Lock hierarchy: Hub.mu -> Client.mu. 
\* Never acquire Hub.mu while holding a Client.mu.
HierarchyOk == 
    \forall c \in Clients:
        LET c_mu == "client_mu_" \ o c IN
        ~(c_mu \in locksHeld[c] /\ locksWaiting[c] = "hub_mu")

\* Initial State
Init == 
    /\ clientState = [c \in Clients |-> "Idle"]
    /\ locksHeld = [p \in Procs |-> {}]
    /\ locksWaiting = [p \in Procs |-> "None"]
    /\ natsSubscribed = [c \in Clients |-> FALSE]

\* Helper: Acquire lock safely if not held by any other process
AcquireLock(p, lock) ==
    /\ \forall other \in Procs : lock \notin locksHeld[other]
    /\ locksHeld' = [locksHeld EXCEPT ![p] = locksHeld[p] \union {lock}]
    /\ locksWaiting' = [locksWaiting EXCEPT ![p] = "None"]

\* Client c attempts to connect and register
ConnectStart(c) ==
    /\ clientState[c] = "Idle"
    /\ clientState' = [clientState EXCEPT ![c] = "Subscribing"]
    /\ locksWaiting' = [locksWaiting EXCEPT ![c] = "client_mu_" \ o c]
    /\ UNCHANGED <<locksHeld, natsSubscribed>>

ConnectAcquireClientMu(c) ==
    LET c_mu == "client_mu_" \ o c IN
    /\ clientState[c] = "Subscribing"
    /\ locksWaiting[c] = c_mu
    /\ AcquireLock(c, c_mu)
    /\ UNCHANGED <<clientState, natsSubscribed>>

ConnectSubscribeNATS(c) ==
    LET c_mu == "client_mu_" \ o c IN
    /\ clientState[c] = "Subscribing"
    /\ c_mu \in locksHeld[c]
    /\ natsSubscribed' = [natsSubscribed EXCEPT ![c] = TRUE]
    /\ clientState' = [clientState EXCEPT ![c] = "Subscribed"]
    /\ UNCHANGED <<locksHeld, locksWaiting>>

ConnectRegisterHub(c) ==
    /\ clientState[c] = "Subscribed"
    /\ locksWaiting' = [locksWaiting EXCEPT ![c] = "hub_mu"]
    /\ UNCHANGED <<clientState, locksHeld, natsSubscribed>>

ConnectAcquireHubMu(c) ==
    /\ clientState[c] = "Subscribed"
    /\ locksWaiting[c] = "hub_mu"
    /\ AcquireLock(c, "hub_mu")
    /\ UNCHANGED <<clientState, natsSubscribed>>

ConnectComplete(c) ==
    LET c_mu == "client_mu_" \ o c IN
    /\ clientState[c] = "Subscribed"
    /\ "hub_mu" \in locksHeld[c]
    /\ clientState' = [clientState EXCEPT ![c] = "Active"]
    /\ locksHeld' = [locksHeld EXCEPT ![c] = locksHeld[c] \ {"hub_mu", c_mu}]
    /\ UNCHANGED <<locksWaiting, natsSubscribed>>

\* Client c disconnects
DisconnectStart(c) ==
    /\ clientState[c] = "Active"
    /\ clientState' = [clientState EXCEPT ![c] = "Disconnecting"]
    /\ locksWaiting' = [locksWaiting EXCEPT ![c] = "client_mu_" \ o c]
    /\ UNCHANGED <<locksHeld, natsSubscribed>>

DisconnectAcquireClientMu(c) ==
    LET c_mu == "client_mu_" \ o c IN
    /\ clientState[c] = "Disconnecting"
    /\ locksWaiting[c] = c_mu
    /\ AcquireLock(c, c_mu)
    /\ UNCHANGED <<clientState, natsSubscribed>>

DisconnectRelease(c) ==
    LET c_mu == "client_mu_" \ o c IN
    /\ clientState[c] = "Disconnecting"
    /\ c_mu \in locksHeld[c]
    /\ clientState' = [clientState EXCEPT ![c] = "Idle"]
    /\ locksHeld' = [locksHeld EXCEPT ![c] = locksHeld[c] \ {c_mu}]
    /\ natsSubscribed' = [natsSubscribed EXCEPT ![c] = FALSE]
    /\ UNCHANGED <<locksWaiting>>

\* Hub broadcasts messages or performs wildcard eviction
HubBroadcastStart ==
    /\ locksHeld["Hub"] = {}
    /\ locksWaiting' = [locksWaiting EXCEPT !["Hub"] = "hub_mu"]
    /\ UNCHANGED <<clientState, locksHeld, natsSubscribed>>

HubAcquireHubMu ==
    /\ locksWaiting["Hub"] = "hub_mu"
    /\ AcquireLock("Hub", "hub_mu")
    /\ UNCHANGED <<clientState, natsSubscribed>>

HubAcquireClientMu(c) ==
    LET c_mu == "client_mu_" \ o c IN
    /\ "hub_mu" \in locksHeld["Hub"]
    /\ c_mu \notin locksHeld["Hub"]
    /\ locksWaiting["Hub"] = "None"
    /\ \forall other \in Procs : c_mu \notin locksHeld[other]
    /\ locksHeld' = [locksHeld EXCEPT !["Hub"] = locksHeld["Hub"] \union {c_mu}]
    /\ UNCHANGED <<clientState, locksWaiting, natsSubscribed>>

HubReleaseAll ==
    /\ "hub_mu" \in locksHeld["Hub"]
    /\ locksHeld' = [locksHeld EXCEPT !["Hub"] = {}]
    /\ UNCHANGED <<clientState, locksWaiting, natsSubscribed>>

\* Next State Relation
Next == 
    \/ \exists c \in Clients : 
        \/ ConnectStart(c)
        \/ ConnectAcquireClientMu(c)
        \/ ConnectSubscribeNATS(c)
        \/ ConnectRegisterHub(c)
        \/ ConnectAcquireHubMu(c)
        \/ ConnectComplete(c)
        \/ DisconnectStart(c)
        \/ DisconnectAcquireClientMu(c)
        \/ DisconnectRelease(c)
        \/ HubAcquireClientMu(c)
    \/ HubBroadcastStart
    \/ HubAcquireHubMu
    \/ HubReleaseAll

Spec == Init /\ [][Next]_<<clientState, locksHeld, locksWaiting, natsSubscribed>>

=============================================================================
