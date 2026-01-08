struct Node {
    struct Node *next;
    int value;
};

void sll_safe_sum_all(struct Node * root) {
    struct Node *current;
    int sum;
    int dif;
    int sumdif;
    int temp;

    current = root;
    sum = 0;
    dif = 0;

    while(current) {
        temp = current->value;
        sum = sum + temp;
        current = current->next;
    }

    current = root;
    while(current) {
        temp = current->value;
        dif = dif - temp;
        current = current->next;
    }

    sumdif = sum + dif;
    if (sumdif != 0) {
        current->value = 0;
    }
}
