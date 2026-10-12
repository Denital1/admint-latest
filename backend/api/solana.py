import json
from decimal import Decimal, ROUND_HALF_UP
from urllib.request import Request, urlopen


RPC_URLS = {
    "devnet": "https://api.devnet.solana.com",
    "testnet": "https://api.testnet.solana.com",
    "mainnet": "https://api.mainnet-beta.solana.com",
    "localnet": "http://127.0.0.1:8899",
}

LAMPORTS_PER_SOL = Decimal("1000000000")


def _rpc_call(cluster: str, method: str, params: list):
    url = RPC_URLS[cluster]
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def get_signature_status(signature: str, cluster: str) -> dict:
    try:
        response = _rpc_call(
            cluster,
            "getSignatureStatuses",
            [[signature], {"searchTransactionHistory": True}],
        )
        result = response.get("result", {}).get("value", [None])[0]
        if result is None:
            return {
                "ok": False,
                "confirmed": False,
                "message": "Transaction was not found on the selected Solana cluster yet.",
                "retryable": True,
            }
        if result.get("err") is not None:
            return {
                "ok": False,
                "confirmed": False,
                "message": f"Solana reports transaction failure: {result['err']}",
            }
        confirmation = result.get("confirmationStatus")
        return {
            "ok": True,
            "confirmed": confirmation in {"confirmed", "finalized"},
            "confirmation_status": confirmation,
            "retryable": confirmation not in {"confirmed", "finalized"},
            "message": f"Solana status: {confirmation or 'processed'}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "confirmed": False,
            "message": "Could not reach Solana RPC. Please retry confirmation.",
            "retryable": True,
        }


def verify_purchase_transaction(
    *,
    signature: str,
    cluster: str,
    buyer_wallet: str,
    seller_wallet: str,
    price_sol: Decimal,
    mint_address: str,
    not_before=None,
    purchase_id=None,
) -> dict:
    """Verify the important parts of the AdMint purchase transaction.

    This intentionally uses Solana's JSON-RPC instead of giving Django any
    access to a user's private key. It checks the confirmed transaction, the
    buyer/seller SOL transfer, and the one-token SPL mint operation.
    """
    status = get_signature_status(signature, cluster)
    if not status["confirmed"]:
        return status

    try:
        response = _rpc_call(
            cluster,
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )
        result = response.get("result")
        if not result:
            return {
                "ok": False,
                "confirmed": False,
                "message": "Solana confirmed the signature, but transaction details are not available yet.",
                "retryable": True,
            }

        if not_before is not None:
            block_time = result.get("blockTime")
            if block_time is None:
                return {"ok": False, "confirmed": False, "retryable": True, "message": "Transaction timestamp is not available yet. Retry confirmation."}
            if block_time < int(not_before.timestamp()) - 120:
                return {"ok": False, "confirmed": False, "message": "This transaction predates the purchase reservation."}

        meta = result.get("meta") or {}
        if meta.get("err") is not None:
            return {
                "ok": False,
                "confirmed": False,
                "message": f"Solana reports transaction failure: {meta['err']}",
            }

        message = result.get("transaction", {}).get("message", {})
        instructions = message.get("instructions", [])
        account_keys = message.get("accountKeys", [])
        if purchase_id is not None:
            expected_memo = f"AdMint purchase:{purchase_id}"
            if not any(instruction.get("programId") == "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr" and instruction.get("parsed") == expected_memo for instruction in instructions):
                return {"ok": False, "confirmed": False, "message": "This transaction is not linked to the prepared AdMint purchase."}

        buyer_is_signer = any(
            (
                key.get("pubkey") == buyer_wallet
                and key.get("signer") is True
            )
            if isinstance(key, dict)
            else False
            for key in account_keys
        )
        if not buyer_is_signer:
            return {
                "ok": False,
                "confirmed": False,
                "message": "The submitted transaction is not signed by the buyer wallet.",
            }

        expected_lamports = int(
            (price_sol * LAMPORTS_PER_SOL).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )

        has_payment = False
        has_mint = False
        mint_account = None
        mint_count = 0
        initialized = False
        revoked = False
        token_program = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        system_program = "11111111111111111111111111111111"

        for instruction in instructions:
            if instruction.get("program") == "system" and instruction.get("programId") == system_program:
                parsed = instruction.get("parsed") or {}
                info = parsed.get("info") or {}
                if (
                    parsed.get("type") == "transfer"
                    and info.get("source") == buyer_wallet
                    and info.get("destination") == seller_wallet
                    and int(info.get("lamports", -1)) == expected_lamports
                ):
                    has_payment = True

            if instruction.get("program") == "spl-token" and instruction.get("programId") == token_program:
                parsed = instruction.get("parsed") or {}
                info = parsed.get("info") or {}
                if parsed.get("type") in {"initializeMint", "initializeMint2"} and info.get("mint") == mint_address:
                    initialized = info.get("decimals") == 0 and info.get("mintAuthority") == buyer_wallet and info.get("freezeAuthority") is None
                if parsed.get("type") == "setAuthority" and (info.get("mint") or info.get("account")) == mint_address and info.get("authorityType") == "mintTokens":
                    revoked = info.get("authority") == buyer_wallet and info.get("newAuthority") is None
                if parsed.get("type") in {"mintTo", "mintToChecked"} and info.get("mint") == mint_address:
                    mint_count += 1
                if (
                    parsed.get("type") == "mintTo"
                    and info.get("mint") == mint_address
                    and str(info.get("amount")) == "1"
                    and info.get("mintAuthority") == buyer_wallet
                ):
                    has_mint = True
                    mint_account = info.get("account")

        if not has_payment:
            return {
                "ok": False,
                "confirmed": False,
                "message": "The confirmed transaction does not contain the expected SOL payment to the seller.",
            }

        if not has_mint:
            return {
                "ok": False,
                "confirmed": False,
                "message": "The confirmed transaction does not contain the expected one-token Ad Right mint.",
            }

        keys = [key.get("pubkey") if isinstance(key, dict) else key for key in account_keys]
        received = any(
            balance.get("mint") == mint_address and balance.get("owner") == buyer_wallet
            and balance.get("programId") == token_program
            and balance.get("uiTokenAmount", {}).get("amount") == "1"
            and balance.get("uiTokenAmount", {}).get("decimals") == 0
            and type(balance.get("accountIndex")) is int
            and 0 <= balance["accountIndex"] < len(keys)
            and keys[balance["accountIndex"]] == mint_account
            for balance in meta.get("postTokenBalances") or []
        )
        existed_before = any(balance.get("mint") == mint_address for balance in meta.get("preTokenBalances") or [])
        if not (initialized and revoked and received and mint_count == 1 and not existed_before):
            return {"ok": False, "confirmed": False, "message": "The Ad Right must be a new zero-decimal token received by the buyer with mint authority revoked."}

        return {
            "ok": True,
            "confirmed": True,
            "confirmation_status": status.get("confirmation_status"),
            "message": "Solana transaction verified: payment and one-token Ad Right mint confirmed.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "confirmed": False,
            "message": "Could not inspect the transaction. Please retry confirmation.",
            "retryable": True,
        }
