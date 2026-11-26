-- Cofre de chaves por usuário (a chave já chega criptografada pelo app).
-- RLS ligada e sem nenhuma política: só a chave de serviço do servidor consegue ler ou gravar.
create table if not exists public.chaves_usuario (
  sub text primary key,
  email text not null default '',
  chave_cifrada text not null,
  atualizado timestamptz not null default now()
);
alter table public.chaves_usuario enable row level security;
