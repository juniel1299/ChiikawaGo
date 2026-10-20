import 'package:flutter/material.dart';

import '../core/api.dart';
import 'signup.dart';

class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key, required this.api});
  final Api api;
  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen> {
  late final signup = Signup(widget.api);
  final email = TextEditingController(), name = TextEditingController();
  final password = TextEditingController(),
      confirmation = TextEditingController();
  @override
  void dispose() {
    signup.dispose();
    email.dispose();
    name.dispose();
    password.dispose();
    confirmation.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    final result = await signup.submit(
      email: email.text,
      displayName: name.text,
      password: password.text,
      confirmation: confirmation.text,
    );
    if (!mounted) return;
    password.clear();
    confirmation.clear();
    if (result != null) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('가입이 완료됐어요. 로그인해 주세요.')));
      Navigator.pop(context, result);
    }
  }

  Widget field(
    String label,
    String key,
    TextEditingController controller, {
    bool secret = false,
  }) => TextField(
    key: ValueKey('signup_$key'),
    controller: controller,
    enabled: !signup.busy,
    obscureText: secret,
    autocorrect: false,
    enableSuggestions: !secret,
    keyboardType: key == 'email'
        ? TextInputType.emailAddress
        : TextInputType.text,
    decoration: InputDecoration(
      labelText: label,
      errorText: signup.errors[key],
      errorMaxLines: 4,
    ),
  );
  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: signup,
    builder: (context, _) => Scaffold(
      appBar: AppBar(title: const Text('회원가입')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              field('표시 이름', 'display_name', name),
              field('이메일', 'email', email),
              field('비밀번호', 'password', password, secret: true),
              field('비밀번호 확인', 'confirmation', confirmation, secret: true),
              const Text('8자 이상이며 이메일과 다르고, 숫자로만 이루어지지 않은 비밀번호를 사용하세요.'),
              if (signup.message != null)
                Text(
                  signup.message!,
                  style: const TextStyle(color: Colors.red),
                ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: signup.busy ? null : submit,
                child: Text(signup.busy ? '가입 중…' : '가입하기'),
              ),
              TextButton(
                onPressed: signup.busy
                    ? null
                    : () => Navigator.pop(context, email.text.trim()),
                child: const Text('이미 계정이 있어요 · 로그인으로'),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
